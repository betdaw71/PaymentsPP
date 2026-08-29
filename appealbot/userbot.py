"""Telegram *user* client that can see other bots (Mel Transaction Bot).

Bot API cannot receive another bot's messages. A user account can. This process
logs in as that user, watches merchant groups, and POSTs the same
process_message/ payload as appealbot/bot.py.

It never writes ticket text into a provider chat. The backend already strips
counterparty names before forwarding.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import requests
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename, MessageMediaDocument, MessageMediaPhoto

from ticket_detect import (
    env_flag,
    generic_receipt_name,
    inline_button_action,
    is_pdf_document,
    is_receipt_document,
    looks_like_ticket,
    looks_like_ticket_document,
    parse_int_ids,
    parse_usernames,
    should_watch_sender,
)

BACKEND_URL = os.getenv("BACKEND_URL", "http://app:8080/api/v1/bot/appeals")
TGBOT_TOKEN = os.getenv("TGBOT_TOKEN", "")
TELEGRAM_API_ID = (os.getenv("TELEGRAM_API_ID") or "").strip()
TELEGRAM_API_HASH = (os.getenv("TELEGRAM_API_HASH") or "").strip()
TELEGRAM_SESSION_STRING = (os.getenv("TELEGRAM_SESSION_STRING") or "").strip()
WATCH_CHAT_IDS = parse_int_ids(os.getenv("USERBOT_WATCH_CHAT_IDS") or "")
SOURCE_USERNAMES = parse_usernames(os.getenv("USERBOT_SOURCE_USERNAMES") or "")
CLICK_INLINE = env_flag(os.getenv("USERBOT_CLICK_INLINE"))
CLICK_POLL_SEC = max(5, int((os.getenv("USERBOT_CLICK_POLL_SEC") or "8").strip() or "8"))
PENDING_TICKET_TTL_SEC = 15 * 60

HEADERS = {"Authorization": f"Token {TGBOT_TOKEN}"}
CHAT_ROLE_TTL_SEC = 5 * 60
_CHAT_ROLES: dict[int, tuple[str, float]] = {}
_SEEN_MEDIA_GROUPS: dict[str, float] = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("appeal-userbot")


def _api_json(response: requests.Response) -> dict:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except ValueError:
        pass
    body = (response.text or "")[:300]
    logger.error("API non-JSON response %s: %s", response.status_code, body)
    return {"ok": False, "message": f"Ошибка API ({response.status_code})"}


def backend_chat_role(chat_id: int) -> str:
    now = time.time()
    cached = _CHAT_ROLES.get(chat_id)
    if cached and now - cached[1] < CHAT_ROLE_TTL_SEC:
        return cached[0]
    role = "unknown"
    try:
        response = requests.post(
            f"{BACKEND_URL}/chat_role/",
            json={"chat_id": chat_id},
            headers=HEADERS,
            timeout=15,
        )
        payload = _api_json(response)
        if payload.get("ok"):
            role = (payload.get("role") or "unknown").strip().lower() or "unknown"
    except requests.RequestException:
        logger.warning("chat_role lookup failed chat_id=%s", chat_id, exc_info=True)
    _CHAT_ROLES[chat_id] = (role, now)
    return role


def backend_process_message(
    chat_id: int,
    message_id: int,
    text: str,
    file_bytes: bytes,
    filename: str,
    ticket_file_bytes: bytes | None = None,
) -> dict:
    files = {}
    if file_bytes:
        files["file"] = (filename or "receipt.bin", file_bytes)
    if ticket_file_bytes:
        files["ticket_file"] = ("ticket.pdf", ticket_file_bytes)
    data = {
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "text": text or "",
    }
    url = f"{BACKEND_URL}/process_message/"
    if files:
        response = requests.post(url, data=data, files=files, headers=HEADERS, timeout=60)
    else:
        response = requests.post(url, data=data, headers=HEADERS, timeout=60)
    payload = _api_json(response)
    payload.setdefault("recognized", False)
    payload.setdefault("outcome", "rejected")
    return payload


def backend_pending_inline_clicks() -> list[dict]:
    response = requests.get(
        f"{BACKEND_URL}/pending_inline_clicks/",
        headers=HEADERS,
        timeout=15,
    )
    payload = _api_json(response)
    items = payload.get("items") or []
    return [item for item in items if isinstance(item, dict)]


def backend_mark_inline_clicked(appeal_id: str) -> None:
    requests.post(
        f"{BACKEND_URL}/mark_inline_clicked/",
        json={"id": appeal_id},
        headers=HEADERS,
        timeout=15,
    )


def _skip_chat(chat_id: int) -> bool:
    if WATCH_CHAT_IDS and chat_id not in WATCH_CHAT_IDS:
        return True
    role = backend_chat_role(chat_id)
    if role == "provider":
        logger.info("ignore provider chat_id=%s", chat_id)
        return True
    return False


def _claim_media_group(chat_id: int, media_group_id) -> bool:
    if not media_group_id:
        return True
    now = time.time()
    stale = [key for key, ts in _SEEN_MEDIA_GROUPS.items() if now - ts > PENDING_TICKET_TTL_SEC]
    for key in stale:
        _SEEN_MEDIA_GROUPS.pop(key, None)
    key = f"{chat_id}:{media_group_id}"
    if key in _SEEN_MEDIA_GROUPS:
        return False
    _SEEN_MEDIA_GROUPS[key] = now
    return True


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
    """Return (receipt_bytes, receipt_name, ticket_pdf_or_none)."""
    if not message.media:
        return b"", "", None
    mime, name = _document_meta(message)
    caption = message.raw_text or ""
    data = await client.download_media(message, file=bytes)
    if not data:
        return b"", "", None
    is_photo = isinstance(message.media, MessageMediaPhoto) or bool(getattr(message, "photo", None))
    if looks_like_ticket_document(mime, name, caption) or (is_pdf_document(mime, name) and looks_like_ticket(caption)):
        return b"", "", data
    if is_photo or is_receipt_document(mime, name):
        return data, generic_receipt_name(name, data), None
    return b"", "", None


async def _react(message, emoji: str) -> None:
    try:
        react = getattr(message, "react", None)
        if callable(react):
            await react(emoji)
            return
        from telethon.tl.functions.messages import SendReactionRequest
        from telethon.tl.types import ReactionEmoji

        await message.client(
            SendReactionRequest(
                peer=await message.get_input_chat(),
                msg_id=message.id,
                reaction=[ReactionEmoji(emoticon=emoji)],
            )
        )
    except Exception as exc:
        logger.warning("userbot react failed msg=%s: %s", message.id, exc)


async def _click_inline(client: TelegramClient, chat_id: int, message_id: int, approved: bool) -> str:
    want = "approve" if approved else "reject"
    try:
        message = await client.get_messages(chat_id, ids=message_id)
    except Exception:
        logger.warning("get_messages failed chat=%s msg=%s", chat_id, message_id, exc_info=True)
        return "error"
    if not message:
        return "no_button"
    markup = getattr(message, "reply_markup", None)
    rows = getattr(markup, "rows", None) or []
    for row in rows:
        for button in getattr(row, "buttons", None) or []:
            action = inline_button_action(getattr(button, "text", "") or "")
            if action != want:
                continue
            try:
                await message.click(text=button.text)
                logger.info("clicked %s on chat=%s msg=%s", want, chat_id, message_id)
                return "clicked"
            except Exception:
                logger.warning("click failed chat=%s msg=%s", chat_id, message_id, exc_info=True)
                return "error"
    return "no_button"


def _configured() -> bool:
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH or not TELEGRAM_SESSION_STRING:
        return False
    try:
        int(TELEGRAM_API_ID)
    except ValueError:
        return False
    return True


async def _on_new_message(event: events.NewMessage.Event, client: TelegramClient) -> None:
    message = event.message
    if message is None:
        return
    chat_id = event.chat_id
    if chat_id is None or _skip_chat(int(chat_id)):
        return

    sender = await event.get_sender()
    username = (getattr(sender, "username", None) or "") if sender else ""
    is_bot = bool(getattr(sender, "bot", False)) if sender else False
    if not should_watch_sender(
        is_self=bool(event.out),
        is_bot=is_bot,
        username=username,
        allowed_usernames=SOURCE_USERNAMES,
    ):
        return

    text = (message.raw_text or "").strip()
    if not looks_like_ticket(text):
        return
    if not _claim_media_group(int(chat_id), getattr(message, "grouped_id", None)):
        return

    logger.info(
        "userbot ingest chat=%s msg=%s from=%s text=%r",
        chat_id,
        message.id,
        username,
        text[:180],
    )
    file_bytes, filename, ticket_bytes = await _download_payload(client, message)
    try:
        payload = await asyncio.to_thread(
            backend_process_message,
            int(chat_id),
            int(message.id),
            text,
            file_bytes,
            filename,
            ticket_bytes,
        )
    except requests.RequestException:
        logger.exception("backend request failed")
        await _react(message, "👎")
        return

    if payload.get("skip"):
        return
    outcome = payload.get("outcome") or "rejected"
    if payload.get("recognized") or payload.get("ok") or outcome == "await_receipt":
        await _react(message, "👀")
    if outcome == "success":
        await _react(message, "👍")
        return
    if outcome in {"pending", "partial", "await_receipt"}:
        return
    await _react(message, "👎")


async def _click_loop(client: TelegramClient) -> None:
    while True:
        await asyncio.sleep(CLICK_POLL_SEC)
        if not CLICK_INLINE:
            continue
        try:
            items = await asyncio.to_thread(backend_pending_inline_clicks)
        except requests.RequestException:
            logger.warning("pending_inline_clicks failed", exc_info=True)
            continue
        for item in items:
            appeal_id = str(item.get("id") or "")
            chat_id = item.get("chat_id")
            message_id = item.get("message_id")
            approved = bool(item.get("approved"))
            if not appeal_id or chat_id is None or message_id is None:
                continue
            result = await _click_inline(client, int(chat_id), int(message_id), approved)
            if result in {"clicked", "no_button"}:
                try:
                    await asyncio.to_thread(backend_mark_inline_clicked, appeal_id)
                except requests.RequestException:
                    logger.warning("mark_inline_clicked failed id=%s", appeal_id, exc_info=True)


async def run() -> None:
    if not _configured():
        raise SystemExit(
            "Appeal userbot is not configured. Set TELEGRAM_API_ID, TELEGRAM_API_HASH, "
            "TELEGRAM_SESSION_STRING (see appealbot/USERBOT.txt)"
        )
    if not TGBOT_TOKEN:
        logger.warning("TGBOT_TOKEN is empty — API calls will fail")

    client = TelegramClient(
        StringSession(TELEGRAM_SESSION_STRING),
        int(TELEGRAM_API_ID),
        TELEGRAM_API_HASH,
    )

    @client.on(events.NewMessage(incoming=True))
    async def handler(event: events.NewMessage.Event) -> None:
        try:
            await _on_new_message(event, client)
        except Exception:
            logger.exception("userbot handler failed")

    await client.start()
    me = await client.get_me()
    logger.info(
        "Appeal userbot started as id=%s username=%s backend=%s watch_chats=%s sources=%s click_inline=%s",
        me.id,
        getattr(me, "username", None) or "",
        BACKEND_URL,
        sorted(WATCH_CHAT_IDS) or "any-non-provider",
        sorted(SOURCE_USERNAMES) or "any-bot",
        CLICK_INLINE,
    )
    click_task = asyncio.create_task(_click_loop(client))
    try:
        await client.run_until_disconnected()
    finally:
        click_task.cancel()


if __name__ == "__main__":
    asyncio.run(run())
