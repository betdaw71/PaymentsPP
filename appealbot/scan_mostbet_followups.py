"""Скан CX<>Avapay_Op: уточняющие сообщения → статусы апелляций Mostbet.

Читает историю чата мониторинг-аккаунтом (Telethon), находит follow-up
(any news? / any update? / Does the receipt… + UUID / id / id / id),
дергает backend lookup и печатает сводку в консоль.

Запуск на проде (из ~/project):

  docker compose --profile userbot run --rm --no-deps \\
    -e HOURS=168 -e LIMIT_MESSAGES=3000 \\
    appeal-userbot python scan_mostbet_followups.py

Опционально:

  MOSTBET_CX_CHAT_ID=-100…     # иначе ищем диалог по title «Avapay_Op» / «CX»
  HOURS=168                    # окно истории
  LIMIT_MESSAGES=3000          # потолок сообщений
  INCLUDE_ALL_CX=1             # ещё все CX slash-линии без follow-up текста
  OPEN_ONLY=1                  # печатать только ещё открытые / без апелляции
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests
from telethon import TelegramClient
from telethon.sessions import StringSession

from ticket_detect import (
    extract_cx_slash_uuids,
    extract_uuids,
    is_followup_chatter,
    parse_int_ids,
)

BACKEND_URL = (os.getenv("BACKEND_URL") or "http://app:8080/api/v1/bot/appeals").rstrip("/")
TGBOT_TOKEN = os.getenv("TGBOT_TOKEN", "")
TELEGRAM_API_ID = (os.getenv("TELEGRAM_API_ID") or "").strip()
TELEGRAM_API_HASH = (os.getenv("TELEGRAM_API_HASH") or "").strip()
TELEGRAM_SESSION_STRING = (os.getenv("TELEGRAM_SESSION_STRING") or "").strip()
WATCH_CHAT_IDS = parse_int_ids(os.getenv("USERBOT_WATCH_CHAT_IDS") or "")

HOURS = int((os.getenv("HOURS") or "168").strip() or "168")
LIMIT_MESSAGES = int((os.getenv("LIMIT_MESSAGES") or "3000").strip() or "3000")
INCLUDE_ALL_CX = (os.getenv("INCLUDE_ALL_CX") or "").strip().lower() in {"1", "true", "yes", "on"}
OPEN_ONLY = (os.getenv("OPEN_ONLY") or "").strip().lower() in {"1", "true", "yes", "on"}

CHAT_TITLE_HINTS = ("avapay_op", "cx<>avapay", "cx< >avapay", "cx avapay", "mostbet")
OPEN_APPEAL = {"created", "sent_to_provider", "awaiting_reject_reason"}
HEADERS = {"Authorization": f"Token {TGBOT_TOKEN}"}


@dataclass
class FollowHit:
    uuid: str
    message_ids: list[int] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    senders: list[str] = field(default_factory=list)
    dates: list[datetime] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)  # followup | cx_line


def _short(value, n: int = 72) -> str:
    text = (str(value) if value is not None else "").replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _require_session() -> tuple[int, str, str]:
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH or not TELEGRAM_SESSION_STRING:
        raise SystemExit(
            "Нужны TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION_STRING "
            "(те же, что у appeal-userbot)."
        )
    try:
        return int(TELEGRAM_API_ID), TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING
    except ValueError as exc:
        raise SystemExit("TELEGRAM_API_ID must be an integer") from exc


def _chat_id_from_env() -> int | None:
    raw = (os.getenv("MOSTBET_CX_CHAT_ID") or "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError as exc:
            raise SystemExit(f"MOSTBET_CX_CHAT_ID invalid: {raw}") from exc
    return None


def _title_matches(title: str) -> bool:
    lowered = (title or "").lower().replace(" ", "")
    if "avapay_op" in lowered or "avapayop" in lowered:
        return True
    if "cx" in lowered and "avapay" in lowered:
        return True
    return False


async def _resolve_chat(client: TelegramClient) -> tuple[int, str]:
    forced = _chat_id_from_env()
    if forced is not None:
        entity = await client.get_entity(forced)
        title = getattr(entity, "title", None) or getattr(entity, "username", None) or str(forced)
        return forced, str(title)

    matches: list[tuple[int, str]] = []
    async for dialog in client.iter_dialogs():
        title = (dialog.name or dialog.title or "").strip()
        if not _title_matches(title):
            continue
        chat_id = int(dialog.id)
        matches.append((chat_id, title))

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print("Несколько чатов похожи на Mostbet CX — укажите MOSTBET_CX_CHAT_ID:")
        for chat_id, title in matches:
            watched = "watch" if chat_id in WATCH_CHAT_IDS else ""
            print(f"  {chat_id}  {title}  {watched}")
        raise SystemExit(2)

    # fallback: любой watch chat, чей title не Melbet/Panda/Aggrepay
    for chat_id in sorted(WATCH_CHAT_IDS):
        try:
            entity = await client.get_entity(chat_id)
        except Exception:
            continue
        title = getattr(entity, "title", None) or str(chat_id)
        if _title_matches(str(title)):
            return chat_id, str(title)

    raise SystemExit(
        "Чат CX<>Avapay_Op не найден. Задайте MOSTBET_CX_CHAT_ID=-100… "
        "или добавьте группу в USERBOT_WATCH_CHAT_IDS."
    )


def _message_text(message) -> str:
    parts: list[str] = []
    raw = (message.message or message.text or "") or ""
    if raw.strip():
        parts.append(raw.strip())
    # filename sometimes carries context; keep short
    if message.file and getattr(message.file, "name", None):
        parts.append(str(message.file.name))
    return "\n".join(parts)


def _sender_label(message) -> str:
    sender = message.sender
    if sender is None:
        return "?"
    username = getattr(sender, "username", None)
    if username:
        return f"@{username}"
    first = (getattr(sender, "first_name", None) or "").strip()
    last = (getattr(sender, "last_name", None) or "").strip()
    name = f"{first} {last}".strip()
    return name or str(getattr(sender, "id", "?"))


def _collect_uuids_from_message(message, reply_text: str | None) -> tuple[list[str], str]:
    """Return (uuids, kind) where kind is followup|cx_line|none."""
    text = _message_text(message)
    combined = text
    if reply_text:
        combined = f"{text}\n{reply_text}"

    followup = is_followup_chatter(text) or is_followup_chatter(combined)
    uuids = extract_cx_slash_uuids(combined) or extract_uuids(combined)

    if followup and uuids:
        return uuids, "followup"
    if INCLUDE_ALL_CX and extract_cx_slash_uuids(text):
        return extract_cx_slash_uuids(text), "cx_line"
    # reply quoting a CX line + short ask without keyword still counts if reply has UUID context
    if followup and not uuids and reply_text:
        quoted = extract_cx_slash_uuids(reply_text) or extract_uuids(reply_text)
        if quoted:
            return quoted, "followup"
    return [], "none"


def lookup_uuid(uuid_value: str) -> dict:
    try:
        response = requests.get(
            f"{BACKEND_URL}/lookup/",
            params={"q": uuid_value},
            headers=HEADERS,
            timeout=30,
        )
    except requests.RequestException as exc:
        return {"ok": False, "message": f"API error: {exc}"}
    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "message": f"non-JSON {response.status_code}"}
    if not isinstance(payload, dict):
        return {"ok": False, "message": "bad payload"}
    return payload


def _appeal_summary(data: dict) -> tuple[str, str]:
    """Return (appeal_status_label, detail)."""
    appeals = data.get("appeals") or []
    if not appeals:
        return "NO_APPEAL", "тикет не зарегистрирован"
    latest = appeals[0]
    status = (latest.get("status") or "—").strip()
    created = latest.get("created_at") or ""
    extra = f"appeal={latest.get('id')} at={created}"
    if len(appeals) > 1:
        extra += f" (+{len(appeals) - 1} older)"
    return status, extra


def _is_interesting(appeal_status: str, found: bool) -> bool:
    if not found:
        return True
    if appeal_status in OPEN_APPEAL or appeal_status == "NO_APPEAL":
        return True
    if appeal_status in {"failed", "no_provider_chat", "duplicate"}:
        return True
    return False


async def scan() -> int:
    api_id, api_hash, session = _require_session()
    since = datetime.now(timezone.utc) - timedelta(hours=HOURS)

    client = TelegramClient(StringSession(session), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit("TELEGRAM_SESSION_STRING невалидна — перелогиньтесь userbot_login.py")

    chat_id, title = await _resolve_chat(client)
    print("=" * 88)
    print(f"Mostbet CX follow-ups → appeal status")
    print(f"chat={chat_id}  title={title!r}  window={HOURS}h  since={since.isoformat()}")
    print(f"include_all_cx={INCLUDE_ALL_CX}  open_only={OPEN_ONLY}  limit={LIMIT_MESSAGES}")
    print("=" * 88)

    hits: dict[str, FollowHit] = {}
    scanned = 0
    followup_msgs = 0
    reply_cache: dict[int, str] = {}

    async for message in client.iter_messages(chat_id, limit=LIMIT_MESSAGES):
        scanned += 1
        msg_date = message.date
        if msg_date is not None:
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)
            if msg_date < since:
                break

        reply_text = None
        if message.reply_to and message.reply_to.reply_to_msg_id:
            rid = int(message.reply_to.reply_to_msg_id)
            if rid in reply_cache:
                reply_text = reply_cache[rid]
            else:
                try:
                    replied = await client.get_messages(chat_id, ids=rid)
                    reply_text = _message_text(replied) if replied else ""
                    reply_cache[rid] = reply_text
                except Exception:
                    reply_text = ""

        text = _message_text(message)
        if message.id is not None:
            reply_cache[int(message.id)] = text

        uuids, kind = _collect_uuids_from_message(message, reply_text)
        if kind == "none" or not uuids:
            continue
        followup_msgs += 1
        sender = _sender_label(message)
        for uuid_value in uuids:
            hit = hits.get(uuid_value)
            if hit is None:
                hit = FollowHit(uuid=uuid_value)
                hits[uuid_value] = hit
            hit.message_ids.append(int(message.id))
            hit.texts.append(_short(text, 90))
            hit.senders.append(sender)
            hit.dates.append(msg_date or datetime.now(timezone.utc))
            hit.kinds.append(kind)

    await client.disconnect()

    print(f"\nscanned_messages={scanned}  matched_messages={followup_msgs}  unique_uuids={len(hits)}")
    if not hits:
        print("Уточняющих сообщений с UUID не найдено.")
        return 0

    rows: list[dict] = []
    counters: dict[str, int] = defaultdict(int)

    print("\n" + "-" * 88)
    print(
        f"{'UUID':36}  {'asks':>4}  {'appeal':22}  {'pay_in':8}  {'order':18}  "
        f"{'psp/merchant':20}  last_ask"
    )
    print("-" * 88)

    for uuid_value, hit in sorted(
        hits.items(),
        key=lambda item: max(item[1].dates) if item[1].dates else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    ):
        payload = lookup_uuid(uuid_value)
        found = bool(payload.get("ok") and payload.get("data"))
        data = payload.get("data") or {}
        if found:
            appeal_status, appeal_detail = _appeal_summary(data)
            pay_st = data.get("status") or "—"
            order_st = data.get("in_order_status") or "—"
            merchant = data.get("merchant") or "—"
            amount = data.get("amount") or ""
            pay_in = (data.get("pay_in_id") or "")[:8] or "—"
            label = f"{merchant}"
            if amount:
                label = f"{merchant} {amount}"
        else:
            appeal_status = "NOT_FOUND"
            appeal_detail = payload.get("message") or "нет в БД"
            pay_st = "—"
            order_st = "—"
            label = "—"
            pay_in = "—"

        interesting = _is_interesting(appeal_status, found)
        counters[appeal_status] += 1
        if interesting:
            counters["interesting"] += 1
        else:
            counters["closed_ok"] += 1

        if OPEN_ONLY and not interesting:
            continue

        last_ask = max(hit.dates).strftime("%m-%d %H:%M") if hit.dates else "—"
        asks = len(hit.message_ids)
        print(
            f"{uuid_value:36}  {asks:4d}  {appeal_status:22}  {pay_in:8}  {order_st:18}  "
            f"{_short(label, 20):20}  {last_ask}"
        )
        print(
            f"  └─ pay_in_st={pay_st}  {appeal_detail}  "
            f"from={hit.senders[0] if hit.senders else '?'}  "
            f"msg={_short(hit.texts[0] if hit.texts else '', 70)}"
        )
        rows.append(
            {
                "uuid": uuid_value,
                "asks": asks,
                "appeal_status": appeal_status,
                "interesting": interesting,
            }
        )

    print("-" * 88)
    print("\nСводка по статусам апелляций:")
    for key, value in sorted(counters.items(), key=lambda x: (-x[1], x[0])):
        if key in {"interesting", "closed_ok"}:
            continue
        print(f"  {key:24} {value}")
    print(
        f"\nинтересуют мерчанта (open / no_appeal / failed / not_found): "
        f"{counters.get('interesting', 0)}"
    )
    print(f"уже закрыты у нас (approved/rejected): {counters.get('closed_ok', 0)}")
    print(f"всего UUID из уточнений: {len(hits)}")
    print("\nГотово.")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(scan()))
    except KeyboardInterrupt:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
