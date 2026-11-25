"""Reprocess Melbet Support tickets that got 👎 / never registered.

Scans AvaPay| Melbet | Support 1, finds Mel Transaction Bot tickets with a
receipt, POSTs process_message/ again (after labelled-Заказ fix).

Запуск (из ~/project):

  # сначала dry-run — только список
  docker compose --profile userbot run --rm --no-deps \\
    -e HOURS=72 -e DRY_RUN=1 \\
    appeal-userbot python reprocess_melbet_tickets.py

  # зарегистрировать и отправить провайдеру
  docker compose --profile userbot run --rm --no-deps \\
    -e HOURS=72 -e APPLY=1 \\
    appeal-userbot python reprocess_melbet_tickets.py

Опционально:
  MELBET_CHAT_ID=-1003769960326
  LIMIT_MESSAGES=2000
  ONLY_THUMBS_DOWN=1     # только сообщения с 👎 (по умолчанию 1)
  SKIP_HAS_APPEAL=1      # пропуск если lookup уже видит appeal (по умолчанию 1)
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename, MessageMediaDocument, MessageMediaPhoto

from ticket_detect import (
    attachment_is_ticket_file,
    generic_receipt_name,
    is_receipt_document,
    looks_like_ticket,
    parse_int_ids,
)

BACKEND_URL = (os.getenv("BACKEND_URL") or "http://app:8080/api/v1/bot/appeals").rstrip("/")
TGBOT_TOKEN = os.getenv("TGBOT_TOKEN", "")
TELEGRAM_API_ID = (os.getenv("TELEGRAM_API_ID") or "").strip()
TELEGRAM_API_HASH = (os.getenv("TELEGRAM_API_HASH") or "").strip()
TELEGRAM_SESSION_STRING = (os.getenv("TELEGRAM_SESSION_STRING") or "").strip()
WATCH_CHAT_IDS = parse_int_ids(os.getenv("USERBOT_WATCH_CHAT_IDS") or "")

HOURS = int((os.getenv("HOURS") or "72").strip() or "72")
LIMIT_MESSAGES = int((os.getenv("LIMIT_MESSAGES") or "2000").strip() or "2000")
DRY_RUN = (os.getenv("DRY_RUN") or "").strip().lower() in {"1", "true", "yes", "on"}
APPLY = (os.getenv("APPLY") or "").strip().lower() in {"1", "true", "yes", "on"}
ONLY_THUMBS_DOWN = (os.getenv("ONLY_THUMBS_DOWN") or "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
SKIP_HAS_APPEAL = (os.getenv("SKIP_HAS_APPEAL") or "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

HEADERS = {"Authorization": f"Token {TGBOT_TOKEN}"}
DEFAULT_MELBET_CHAT = -1003769960326


def _short(value, n: int = 90) -> str:
    text = (str(value) if value is not None else "").replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _require_session() -> tuple[int, str, str]:
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH or not TELEGRAM_SESSION_STRING:
        raise SystemExit(
            "Нужны TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION_STRING"
        )
    try:
        return int(TELEGRAM_API_ID), TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING
    except ValueError as exc:
        raise SystemExit("TELEGRAM_API_ID must be an integer") from exc


def _chat_id_from_env() -> int | None:
    raw = (os.getenv("MELBET_CHAT_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit(f"MELBET_CHAT_ID invalid: {raw}") from exc


def _title_is_melbet(title: str) -> bool:
    lowered = (title or "").lower().replace(" ", "")
    if "melbet" in lowered and "support" in lowered:
        return True
    if "мелбет" in (title or "").lower():
        return True
    return False


async def _resolve_chat(client: TelegramClient) -> tuple[int, str]:
    forced = _chat_id_from_env()
    if forced is not None:
        entity = await client.get_entity(forced)
        title = getattr(entity, "title", None) or str(forced)
        return forced, str(title)

    matches: list[tuple[int, str]] = []
    async for dialog in client.iter_dialogs():
        title = (dialog.name or dialog.title or "").strip()
        if _title_is_melbet(title):
            matches.append((int(dialog.id), title))

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print("Несколько Melbet-чатов — укажите MELBET_CHAT_ID:")
        for chat_id, title in matches:
            print(f"  {chat_id}  {title}")
        raise SystemExit(2)

    try:
        entity = await client.get_entity(DEFAULT_MELBET_CHAT)
        title = getattr(entity, "title", None) or str(DEFAULT_MELBET_CHAT)
        return DEFAULT_MELBET_CHAT, str(title)
    except Exception as exc:
        raise SystemExit(
            f"Melbet chat {DEFAULT_MELBET_CHAT} недоступен: {exc}. "
            "Задайте MELBET_CHAT_ID=..."
        ) from exc


def _message_text(message) -> str:
    return ((message.message or message.text or "") or "").strip()


def _has_thumbs_down(message) -> bool:
    reactions = getattr(message, "reactions", None)
    results = getattr(reactions, "results", None) if reactions else None
    if not results:
        return False
    for row in results:
        emoticon = getattr(getattr(row, "reaction", None), "emoticon", None) or ""
        if emoticon == "👎":
            return True
    return False


def _has_success_react(message) -> bool:
    reactions = getattr(message, "reactions", None)
    results = getattr(reactions, "results", None) if reactions else None
    if not results:
        return False
    for row in results:
        emoticon = getattr(getattr(row, "reaction", None), "emoticon", None) or ""
        if emoticon in {"👍", "👀"}:
            return True
    return False


def _document_meta(message) -> tuple[str, str]:
    media = message.media
    if not isinstance(media, MessageMediaDocument) or media.document is None:
        return "", ""
    mime = getattr(media.document, "mime_type", "") or ""
    name = ""
    for attr in media.document.attributes or []:
        if isinstance(attr, DocumentAttributeFilename):
            name = attr.file_name or ""
            break
    return mime, name


async def _download_payload(client: TelegramClient, message) -> tuple[bytes, str, bytes | None]:
    if not message.media:
        return b"", "", None
    mime, name = _document_meta(message)
    caption = _message_text(message)
    data = await client.download_media(message, file=bytes)
    if not data:
        return b"", "", None
    is_photo = isinstance(message.media, MessageMediaPhoto) or bool(getattr(message, "photo", None))
    if attachment_is_ticket_file(mime, name, caption):
        return b"", "", data
    if is_photo or is_receipt_document(mime, name):
        safe = generic_receipt_name(name, data)
        return data, (name or "").strip() or safe, None
    return b"", "", None


def _lookup(query: str) -> dict:
    try:
        response = requests.get(
            f"{BACKEND_URL}/lookup/",
            params={"q": query},
            headers=HEADERS,
            timeout=30,
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {"ok": False}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _process(
    chat_id: int,
    message_id: int,
    text: str,
    file_bytes: bytes,
    filename: str,
    ticket_file_bytes: bytes | None,
) -> dict:
    files = {}
    upload_name = generic_receipt_name(filename, file_bytes) if file_bytes else (filename or "receipt.bin")
    if file_bytes:
        files["file"] = (upload_name or "receipt.bin", file_bytes)
    if ticket_file_bytes:
        files["ticket_file"] = ("ticket.pdf", ticket_file_bytes)
    merged = (text or "").strip()
    original = (filename or "").strip()
    if original and original not in merged and not original.startswith("receipt."):
        merged = f"{merged}\n{original}".strip() if merged else original
    data = {
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "text": merged,
        "original_filename": original,
    }
    url = f"{BACKEND_URL}/process_message/"
    if files:
        response = requests.post(url, data=data, files=files, headers=HEADERS, timeout=90)
    else:
        response = requests.post(url, data=data, headers=HEADERS, timeout=90)
    try:
        payload = response.json()
    except ValueError:
        payload = {"ok": False, "outcome": "rejected", "message": response.text[:200]}
    if not isinstance(payload, dict):
        payload = {"ok": False, "outcome": "rejected", "message": "bad payload"}
    payload.setdefault("outcome", "rejected")
    return payload


def _order_hint(text: str) -> str:
    for line in (text or "").splitlines():
        if "заказ" in line.lower() or "тикет" in line.lower() or "номер в" in line.lower():
            return line.strip()
    return _short(text, 60)


async def run() -> int:
    if not DRY_RUN and not APPLY:
        print("Укажите DRY_RUN=1 (список) или APPLY=1 (отправить).")
        return 2

    api_id, api_hash, session = _require_session()
    since = datetime.now(timezone.utc) - timedelta(hours=HOURS)
    client = TelegramClient(StringSession(session), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit("TELEGRAM_SESSION_STRING невалидна")

    chat_id, title = await _resolve_chat(client)
    print("=" * 88)
    print("Melbet ticket reprocess")
    print(f"chat={chat_id} title={title!r} hours={HOURS} dry_run={DRY_RUN} apply={APPLY}")
    print(f"only_thumbs_down={ONLY_THUMBS_DOWN} skip_has_appeal={SKIP_HAS_APPEAL}")
    print("=" * 88)

    scanned = 0
    candidates = 0
    stats = {"success": 0, "pending": 0, "partial": 0, "rejected": 0, "duplicate": 0, "skip": 0, "other": 0}

    async for message in client.iter_messages(chat_id, limit=LIMIT_MESSAGES):
        scanned += 1
        msg_date = message.date
        if msg_date is not None:
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)
            if msg_date < since:
                break

        text = _message_text(message)
        if not looks_like_ticket(text):
            continue
        if not message.media:
            continue
        # Already accepted by userbot → skip
        if _has_success_react(message):
            continue
        # Default: 👎 or no reactions. ONLY_THUMBS_DOWN=0 → любой без 👀/👍
        if ONLY_THUMBS_DOWN and not _has_thumbs_down(message):
            reactions = getattr(message, "reactions", None)
            if reactions and getattr(reactions, "results", None):
                continue

        sender = message.sender
        is_bot = bool(getattr(sender, "bot", False))
        uname = (getattr(sender, "username", None) or "") if sender else ""
        if sender and not is_bot and "тикет" not in text.lower():
            continue

        receipt_bytes, receipt_name, ticket_bytes = await _download_payload(client, message)
        if not receipt_bytes and not ticket_bytes:
            continue

        candidates += 1
        when = msg_date.strftime("%m-%d %H:%M") if msg_date else "?"
        hint = _order_hint(text)

        lookup_q = ""
        for line in text.splitlines():
            if "заказ" in line.lower():
                lookup_q = line.split(":")[-1].strip() if ":" in line else ""
                break
        if not lookup_q:
            lookup_q = text[:80]

        already = False
        if SKIP_HAS_APPEAL and lookup_q:
            payload = _lookup(lookup_q)
            data = payload.get("data") or {}
            appeals = data.get("appeals") or []
            openish = [
                a
                for a in appeals
                if (a.get("status") or "")
                not in {"failed", "no_provider_chat", "duplicate"}
            ]
            if openish:
                already = True
                print(f"SKIP msg={message.id} {when} already appeal={openish[0].get('status')}  {hint}")
                stats["skip"] += 1
                continue

        print(f"{'DRY ' if DRY_RUN else 'APPLY'} msg={message.id} {when} bot={uname or is_bot}  {hint}")

        if DRY_RUN:
            stats["other"] += 1
            continue

        try:
            result = _process(
                int(chat_id),
                int(message.id),
                text,
                receipt_bytes,
                receipt_name,
                ticket_bytes,
            )
        except requests.RequestException as exc:
            print(f"  ERROR request: {exc}")
            stats["rejected"] += 1
            continue

        outcome = (result.get("outcome") or "rejected").strip()
        stats[outcome] = stats.get(outcome, 0) + 1
        print(
            f"  → outcome={outcome} ok={result.get('ok')} "
            f"msg={_short(result.get('message'), 100)}"
        )

        # refresh reaction hint for ops
        if outcome in {"success", "pending", "partial"}:
            try:
                await message.react("👀")
            except Exception:
                pass

    await client.disconnect()
    print("-" * 88)
    print(f"scanned={scanned} candidates={candidates}")
    for key, value in sorted(stats.items()):
        if value:
            print(f"  {key}: {value}")
    print("Готово.")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(run()))
    except KeyboardInterrupt:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
