"""Reprocess Aggrepay DISPUT tickets that were never ingested.

Chat: Avapay x AGGREpay DISPUT — SUPPORT posts
  ``ac19…g`` + UUID + bank + amount + PDF/URL.

Запуск:

  docker compose --profile userbot run --rm --no-deps \\
    -e HOURS=72 -e DRY_RUN=1 \\
    appeal-userbot python reprocess_aggrepay_tickets.py

  docker compose --profile userbot run --rm --no-deps \\
    -e HOURS=72 -e APPLY=1 \\
    appeal-userbot python reprocess_aggrepay_tickets.py

  AGGREPAY_CHAT_ID=-1004386075514   # если автопоиск не сработал
"""

from __future__ import annotations

import asyncio
import os
import re
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
LIMIT_MESSAGES = int((os.getenv("LIMIT_MESSAGES") or "1500").strip() or "1500")
DRY_RUN = (os.getenv("DRY_RUN") or "").strip().lower() in {"1", "true", "yes", "on"}
APPLY = (os.getenv("APPLY") or "").strip().lower() in {"1", "true", "yes", "on"}
SKIP_HAS_APPEAL = (os.getenv("SKIP_HAS_APPEAL") or "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

HEADERS = {"Authorization": f"Token {TGBOT_TOKEN}"}
DEFAULT_CHAT = -1004386075514
AGGREPAY_ID_RE = re.compile(
    r"[0-9a-fA-F]{9}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}g\b",
    re.IGNORECASE,
)
RECEIPT_URL_RE = re.compile(r"https?://\S+\.pdf\b", re.IGNORECASE)


def _short(value, n: int = 90) -> str:
    text = (str(value) if value is not None else "").replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _require_session() -> tuple[int, str, str]:
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH or not TELEGRAM_SESSION_STRING:
        raise SystemExit("Нужны TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION_STRING")
    return int(TELEGRAM_API_ID), TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING


def _chat_id_from_env() -> int | None:
    raw = (os.getenv("AGGREPAY_CHAT_ID") or "").strip()
    if not raw:
        return None
    return int(raw)


def _title_is_aggrepay(title: str) -> bool:
    low = (title or "").lower()
    if "aggrepay" in low or "агрепей" in low or "аггрепей" in low:
        return True
    if "disput" in low and "avapay" in low:
        return True
    return False


async def _resolve_chat(client: TelegramClient) -> tuple[int, str]:
    forced = _chat_id_from_env()
    if forced is not None:
        entity = await client.get_entity(forced)
        return forced, str(getattr(entity, "title", None) or forced)

    matches: list[tuple[int, str]] = []
    async for dialog in client.iter_dialogs():
        title = (dialog.name or dialog.title or "").strip()
        if _title_is_aggrepay(title):
            matches.append((int(dialog.id), title))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print("Несколько Aggrepay-чатов — AGGREPAY_CHAT_ID=")
        for chat_id, title in matches:
            mark = "WATCH" if chat_id in WATCH_CHAT_IDS else ""
            print(f"  {chat_id}  {title}  {mark}")
        raise SystemExit(2)

    try:
        entity = await client.get_entity(DEFAULT_CHAT)
        return DEFAULT_CHAT, str(getattr(entity, "title", None) or DEFAULT_CHAT)
    except Exception as exc:
        raise SystemExit(
            f"Aggrepay chat не найден ({exc}). Задайте AGGREPAY_CHAT_ID= и "
            "проверьте, что мониторинг-аккаунт в группе Avapay x AGGREpay DISPUT."
        ) from exc


def _message_text(message) -> str:
    return ((message.message or message.text or "") or "").strip()


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


def _download_url_pdf(text: str) -> tuple[bytes, str]:
    match = RECEIPT_URL_RE.search(text or "")
    if not match:
        return b"", ""
    url = match.group(0).rstrip(").,]")
    try:
        response = requests.get(url, timeout=60)
        if response.status_code >= 400 or not response.content:
            return b"", ""
        name = url.rsplit("/", 1)[-1] or "receipt.pdf"
        return response.content, name
    except requests.RequestException:
        return b"", ""


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


def _process(chat_id: int, message_id: int, text: str, file_bytes: bytes, filename: str) -> dict:
    files = {}
    upload_name = generic_receipt_name(filename, file_bytes) if file_bytes else (filename or "receipt.bin")
    if file_bytes:
        files["file"] = (upload_name or "receipt.bin", file_bytes)
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
        payload = {"ok": False, "outcome": "rejected"}
    payload.setdefault("outcome", "rejected")
    return payload


def _order_hint(text: str) -> str:
    m = AGGREPAY_ID_RE.search(text or "")
    if m:
        return m.group(0)
    return _short(text, 70)


async def run() -> int:
    if not DRY_RUN and not APPLY:
        print("Укажите DRY_RUN=1 или APPLY=1")
        return 2

    api_id, api_hash, session = _require_session()
    since = datetime.now(timezone.utc) - timedelta(hours=HOURS)
    client = TelegramClient(StringSession(session), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit("TELEGRAM_SESSION_STRING невалидна")

    chat_id, title = await _resolve_chat(client)
    in_watch = chat_id in WATCH_CHAT_IDS if WATCH_CHAT_IDS else True
    print("=" * 88)
    print("Aggrepay DISPUT reprocess")
    print(f"chat={chat_id} title={title!r} hours={HOURS} dry_run={DRY_RUN} apply={APPLY}")
    print(f"in_USERBOT_WATCH_CHAT_IDS={in_watch}  watch={sorted(WATCH_CHAT_IDS) or 'ANY'}")
    if not in_watch:
        print("⚠ чат НЕ в USERBOT_WATCH_CHAT_IDS — live-мониторинг его не читает!")
    print("=" * 88)

    # chat_role check
    try:
        role_resp = requests.post(
            f"{BACKEND_URL}/chat_role/",
            json={"chat_id": chat_id},
            headers=HEADERS,
            timeout=15,
        ).json()
        print(f"backend chat_role={role_resp}")
        if (role_resp.get("role") or "") == "unknown":
            print("⚠ чат не /init — process_message будет skip. Привяжите Aggrepay counterparty.")
    except Exception as exc:
        print(f"chat_role lookup failed: {exc}")

    scanned = 0
    candidates = 0
    stats: dict[str, int] = {}

    async for message in client.iter_messages(chat_id, limit=LIMIT_MESSAGES):
        scanned += 1
        msg_date = message.date
        if msg_date is not None:
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)
            if msg_date < since:
                break

        text = _message_text(message)
        if not looks_like_ticket(text) and not AGGREPAY_ID_RE.search(text):
            continue
        if _has_success_react(message):
            continue

        receipt_bytes, receipt_name, ticket_bytes = await _download_payload(client, message)
        if ticket_bytes and not receipt_bytes:
            receipt_bytes, receipt_name = ticket_bytes, "ticket.pdf"
        if not receipt_bytes:
            receipt_bytes, receipt_name = _download_url_pdf(text)
        if not receipt_bytes and not looks_like_ticket(text):
            continue

        candidates += 1
        when = msg_date.strftime("%m-%d %H:%M") if msg_date else "?"
        hint = _order_hint(text)
        sender = message.sender
        uname = (getattr(sender, "username", None) or getattr(sender, "first_name", None) or "?")

        if SKIP_HAS_APPEAL:
            matched = AGGREPAY_ID_RE.search(text)
            q = matched.group(0) if matched else hint
            payload = _lookup(str(q))
            appeals = (payload.get("data") or {}).get("appeals") or []
            openish = [
                a
                for a in appeals
                if (a.get("status") or "") not in {"failed", "no_provider_chat", "duplicate"}
            ]
            if openish:
                print(f"SKIP msg={message.id} {when} appeal={openish[0].get('status')} {hint}")
                stats["skip"] = stats.get("skip", 0) + 1
                continue

        print(f"{'DRY ' if DRY_RUN else 'APPLY'} msg={message.id} {when} from={uname}  {hint}")
        if DRY_RUN:
            stats["dry"] = stats.get("dry", 0) + 1
            continue

        try:
            result = _process(int(chat_id), int(message.id), text, receipt_bytes, receipt_name)
        except requests.RequestException as exc:
            print(f"  ERROR request: {exc}")
            stats["error"] = stats.get("error", 0) + 1
            continue

        outcome = (result.get("outcome") or "rejected").strip()
        stats[outcome] = stats.get(outcome, 0) + 1
        print(f"  → outcome={outcome} ok={result.get('ok')} msg={_short(result.get('message'), 120)}")
        if outcome in {"success", "pending", "partial"}:
            try:
                await message.react("👀")
            except Exception:
                pass

    await client.disconnect()
    print("-" * 88)
    print(f"scanned={scanned} candidates={candidates}")
    for key, value in sorted(stats.items()):
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
