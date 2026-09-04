import logging
import os
import threading
import time

import requests
import telebot
from telebot.types import Message, ReactionTypeEmoji

from ticket_detect import (
    generic_receipt_name,
    is_pdf_document as _is_pdf_meta,
    is_receipt_document as _is_receipt_meta,
    looks_like_ticket,
    looks_like_ticket_document as _looks_like_ticket_document_meta,
)

BACKEND_URL = os.getenv("BACKEND_URL", "http://app:8080/api/v1/bot/appeals")
TGBOT_TOKEN = os.getenv("TGBOT_TOKEN", "")
TELEBOT_TOKEN = os.getenv("TELEBOT_TOKEN", "")

PENDING_TICKET_TTL_SEC = 15 * 60
# Telegram delivers album items as separate updates; wait briefly so caption+files land together.
MEDIA_GROUP_FLUSH_SEC = float(os.getenv("APPEAL_MEDIA_GROUP_FLUSH_SEC", "1.8"))
_PENDING_TICKETS: dict[int, dict] = {}
_MEDIA_ALBUMS: dict[str, dict] = {}
_MEDIA_ALBUMS_LOCK = threading.Lock()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("appealbot")

bot = telebot.TeleBot(TELEBOT_TOKEN)

HEADERS = {"Authorization": f"Token {TGBOT_TOKEN}"}
CHAT_ROLE_TTL_SEC = 5 * 60
_CHAT_ROLES: dict[int, tuple[str, float]] = {}

HELP_TEXT = (
    "Бот апелляций AvaPay.\n\n"
    "Telegram не отдаёт ботам сообщения других ботов (Mel Transaction Bot). "
    "Тикет сам по себе бот не увидит — нужен ответ человека.\n\n"
    "Как обработать заявку:\n"
    "1. Пришлите ID заявки и чек одним сообщением (фото или файл)\n"
    "2. Или сначала ID / тикет, затем чек\n\n"
    "Команды:\n"
    "/init <uuid контрагента> — регистрация чата\n"
    "/lookup <ID заявки> — все ID по сделке (PayIn, InOrder, PSP, Melbet)\n"
    "/appeal — запомнить тикет и ждать чек\n\n"
    "В BotFather отключите Group Privacy, иначе бот не видит фото в группе."
)


def _set_reaction(chat_id: int, message_id: int, emoji: str) -> None:
    try:
        bot.set_message_reaction(
            chat_id,
            message_id,
            reaction=[ReactionTypeEmoji(emoji)],
            is_big=emoji == "👍",
        )
    except Exception as exc:
        logger.warning("set_message_reaction failed: %s", exc)


def _api_json(response: requests.Response) -> dict:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except ValueError:
        pass
    body = (response.text or "")[:300]
    logger.error("API non-JSON response %s: %s", response.status_code, body)
    return {
        "ok": False,
        "message": f"Ошибка API ({response.status_code})",
        "recognized": False,
        "outcome": "rejected",
    }


def backend_init_chat(chat_id: int, counterparty_id: str, title: str, username: str) -> tuple[bool, str]:
    response = requests.post(
        f"{BACKEND_URL}/init_chat/",
        json={
            "chat_id": chat_id,
            "counterparty_id": counterparty_id,
            "title": title,
            "registered_by_username": username or "",
        },
        headers=HEADERS,
        timeout=30,
    )
    payload = _api_json(response)
    return payload.get("ok", False), payload.get("message", "Ошибка API")


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


def _forget_chat_role(chat_id: int) -> None:
    _CHAT_ROLES.pop(chat_id, None)


def _skip_provider_chat(chat_id: int) -> bool:
    role = backend_chat_role(chat_id)
    if role == "provider":
        logger.info("ignore provider chat_id=%s", chat_id)
        return True
    return False


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


def _audit(message: Message) -> None:
    fu = message.from_user
    document = getattr(message, "document", None)
    logger.info(
        "tg chat=%s msg=%s from_id=%s username=%s is_bot=%s has_photo=%s has_doc=%s mime=%s filename=%s reply_to=%s caption=%r text=%r",
        message.chat.id,
        message.message_id,
        fu.id if fu else None,
        (fu.username if fu else None) or "",
        bool(fu.is_bot) if fu else None,
        bool(message.photo),
        bool(document),
        (document.mime_type if document else None) or "",
        (document.file_name if document else None) or "",
        getattr(getattr(message, "reply_to_message", None), "message_id", None),
        (message.caption or "")[:180],
        (message.text or "")[:180],
    )


@bot.message_handler(commands=["start", "help"])
@bot.channel_post_handler(commands=["start", "help"])
def help_command(message: Message):
    _audit(message)
    bot.reply_to(message, HELP_TEXT)


def backend_lookup(query: str) -> tuple[bool, dict | str]:
    response = requests.get(
        f"{BACKEND_URL}/lookup/",
        params={"q": query},
        headers=HEADERS,
        timeout=30,
    )
    payload = _api_json(response)
    if payload.get("ok"):
        return True, payload.get("data", {})
    return False, payload.get("message", "Заявка не найдена.")


def _format_lookup(data: dict) -> str:
    lines = ["📋 Все ID по сделке:\n"]
    field_labels = [
        ("pay_in_id", "PayIn ID"),
        ("merchant_order_id", "Merchant Order ID"),
        ("in_order_id", "InOrder ID"),
        ("status", "PayIn Status"),
        ("in_order_status", "InOrder Status"),
        ("amount", "Amount"),
        ("merchant", "Merchant"),
        ("melbet_session_id", "Melbet Session ID"),
        ("melbet_order_id", "Melbet Order ID"),
    ]
    for key, label in field_labels:
        val = data.get(key)
        if val:
            lines.append(f"  {label}: {val}")

    # PSP sessions
    psp_names = ["payplat", "gipay", "botonpay", "bitzone", "fairpay", "visionx", "expayone", "protocol", "syndicate"]
    for psp in psp_names:
        ext = data.get(f"{psp}_external_id")
        prov = data.get(f"{psp}_provider_id")
        last_st = data.get(f"{psp}_last_status")
        if ext or prov:
            lines.append(f"\n🔗 {psp.upper()}:")
            if ext:
                lines.append(f"  external_id: {ext}")
            if prov:
                lines.append(f"  provider_id: {prov}")
            if last_st:
                lines.append(f"  last_status: {last_st}")

    appeals = data.get("appeals")
    if appeals:
        lines.append(f"\n📝 Апелляции ({len(appeals)}):")
        for a in appeals:
            lines.append(f"  {a['id']} — {a['status']} ({a['created_at'][:19]})")

    return "\n".join(lines)


@bot.message_handler(commands=["lookup"])
@bot.channel_post_handler(commands=["lookup"])
def lookup_command(message: Message):
    """Lookup all IDs for a deal by any known ID."""
    _audit(message)
    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(message, "Использование: /lookup <ID заявки>\nID может быть PayIn UUID, merchant_order_id, provider ID и т.д.")
        return

    query = parts[1].strip()
    ok, result = backend_lookup(query)
    if not ok:
        bot.reply_to(message, f"❌ {result}")
        return

    bot.reply_to(message, _format_lookup(result))


@bot.message_handler(commands=["init"])
@bot.channel_post_handler(commands=["init"])
def init_command(message: Message):
    _audit(message)
    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "Использование: /init <uuid>")
        return

    counterparty_id = parts[1].strip()
    chat = message.chat
    ok, reply = backend_init_chat(
        chat_id=chat.id,
        counterparty_id=counterparty_id,
        title=chat.title or "",
        username=(message.from_user.username if message.from_user else "") or "",
    )
    _forget_chat_role(chat.id)
    bot.reply_to(message, reply or ("Ок" if ok else "Ошибка"))


@bot.message_handler(commands=["appeal"])
@bot.channel_post_handler(commands=["appeal"])
def appeal_command(message: Message):
    _audit(message)
    if _skip_provider_chat(message.chat.id):
        return
    ticket_text = _collect_appeal_text(message)
    ticket_file_id = _ticket_file_id_from_message(message)
    if not _looks_like_ticket(ticket_text) and not ticket_file_id:
        return
    _remember_ticket(message.chat.id, ticket_text, ticket_file_id=ticket_file_id)
    bot.reply_to(message, "Пришлите чек (фото или файл) вместе с ID заявки.")


def _is_pdf_document(document) -> bool:
    if document is None:
        return False
    return _is_pdf_meta(document.mime_type, document.file_name)


def _is_receipt_document(document) -> bool:
    if document is None:
        return False
    return _is_receipt_meta(document.mime_type, document.file_name)


def _looks_like_ticket_document(document, caption: str | None) -> bool:
    if document is None:
        return False
    return _looks_like_ticket_document_meta(document.mime_type, document.file_name, caption)


def _generic_receipt_name(filename: str | None, content: bytes) -> str:
    return generic_receipt_name(filename, content)


def _looks_like_ticket(text: str) -> bool:
    return looks_like_ticket(text)


def _download_by_file_id(file_id: str) -> bytes | None:
    try:
        file_info = bot.get_file(file_id)
        return bot.download_file(file_info.file_path)
    except Exception:
        logger.warning("download file_id=%s failed", file_id, exc_info=True)
        return None


def _download_file(message: Message | None) -> tuple[bytes, str] | None:
    """Download attachment. Keep original document name for ID mining; provider sanitizes later."""
    if message is None:
        return None
    if message.photo:
        photo = message.photo[-1]
        content = _download_by_file_id(photo.file_id)
        if content is None:
            return None
        return content, "receipt.jpg"

    if message.document and _is_receipt_document(message.document):
        document = message.document
        content = _download_by_file_id(document.file_id)
        if content is None:
            return None
        original = (document.file_name or "").strip()
        # Prefer original name (may contain order id); fall back to magic-based generic.
        return content, original or _generic_receipt_name(document.file_name, content)

    return None


def _remember_ticket(chat_id: int, text: str, ticket_file_id: str | None = None) -> None:
    prev = _PENDING_TICKETS.get(chat_id) or {}
    file_id = ticket_file_id or prev.get("ticket_file_id")
    merged_text = text or prev.get("text") or ""
    if text and prev.get("text") and text.strip() != (prev.get("text") or "").strip():
        # Keep earlier ticket lines if a later caption is only a short add-on.
        if (prev.get("text") or "") not in text:
            merged_text = f"{prev.get('text')}\n{text}".strip()
    _PENDING_TICKETS[chat_id] = {
        "text": merged_text,
        "ts": time.time(),
        "ticket_file_id": file_id,
    }


def _peek_ticket(chat_id: int) -> str:
    item = _PENDING_TICKETS.get(chat_id)
    if not item:
        return ""
    if time.time() - item["ts"] > PENDING_TICKET_TTL_SEC:
        _PENDING_TICKETS.pop(chat_id, None)
        return ""
    return item.get("text") or ""


def _peek_ticket_file_id(chat_id: int) -> str:
    item = _PENDING_TICKETS.get(chat_id)
    if not item:
        return ""
    if time.time() - item["ts"] > PENDING_TICKET_TTL_SEC:
        _PENDING_TICKETS.pop(chat_id, None)
        return ""
    return item.get("ticket_file_id") or ""


def _clear_ticket(chat_id: int) -> None:
    _PENDING_TICKETS.pop(chat_id, None)


def _message_body(message: Message | None) -> str:
    if message is None:
        return ""
    parts = []
    for src in (message.caption, message.text):
        if src and src.strip():
            parts.append(src.strip())
    return "\n".join(parts)


def _ticket_file_id_from_message(message: Message) -> str | None:
    reply = getattr(message, "reply_to_message", None)
    if reply and reply.document and _is_pdf_document(reply.document):
        return reply.document.file_id
    if message.document and _is_pdf_document(message.document):
        caption = _message_body(message)
        if _looks_like_ticket_document(message.document, caption) or _looks_like_ticket(caption):
            return message.document.file_id
    pending = _peek_ticket_file_id(message.chat.id)
    return pending or None


def _collect_appeal_text_from_messages(messages: list[Message], chat_id: int) -> str:
    parts: list[str] = []
    for message in messages:
        own = _message_body(message)
        if own and own not in parts:
            parts.append(own)
        reply = _message_body(getattr(message, "reply_to_message", None))
        if reply and reply not in parts:
            parts.append(reply)
        # Document filenames sometimes carry the merchant order id.
        document = getattr(message, "document", None)
        name = (getattr(document, "file_name", None) or "").strip()
        if name and name not in parts and looks_like_ticket(name):
            parts.append(name)
    combined = "\n".join(parts)
    pending = _peek_ticket(chat_id)
    if pending and pending not in parts:
        # Always merge pending context for albums/retries (caption may land on a later item).
        parts.append(pending)
        combined = "\n".join(parts)
    return combined


def _collect_appeal_text(message: Message) -> str:
    return _collect_appeal_text_from_messages([message], message.chat.id)


def _download_ticket_pdf(message: Message, receipt_file_id: str | None) -> bytes | None:
    file_id = _ticket_file_id_from_message(message)
    if not file_id or file_id == receipt_file_id:
        file_id = _peek_ticket_file_id(message.chat.id) or None
    if not file_id or file_id == receipt_file_id:
        return None
    return _download_by_file_id(file_id)


def _file_id_of(message: Message) -> str | None:
    if message.document:
        return message.document.file_id
    if message.photo:
        return message.photo[-1].file_id
    return None


def _enqueue_media_group(message: Message) -> bool:
    """Buffer album items. Returns True when the caller should process this message now."""
    media_group_id = getattr(message, "media_group_id", None)
    if not media_group_id:
        return True
    key = f"{message.chat.id}:{media_group_id}"
    with _MEDIA_ALBUMS_LOCK:
        stale = [
            album_key
            for album_key, bucket in _MEDIA_ALBUMS.items()
            if time.time() - bucket.get("ts", 0) > PENDING_TICKET_TTL_SEC
        ]
        for album_key in stale:
            old = _MEDIA_ALBUMS.pop(album_key, None)
            timer = (old or {}).get("timer")
            if timer is not None:
                try:
                    timer.cancel()
                except Exception:
                    pass
        bucket = _MEDIA_ALBUMS.get(key)
        if bucket is None:
            bucket = {"messages": [], "ts": time.time(), "timer": None}
            _MEDIA_ALBUMS[key] = bucket
            timer = threading.Timer(MEDIA_GROUP_FLUSH_SEC, _flush_media_group, args=(key,))
            timer.daemon = True
            bucket["timer"] = timer
            timer.start()
        bucket["messages"].append(message)
        bucket["ts"] = time.time()
    return False


def _flush_media_group(key: str) -> None:
    with _MEDIA_ALBUMS_LOCK:
        bucket = _MEDIA_ALBUMS.pop(key, None)
    if not bucket:
        return
    messages = list(bucket.get("messages") or [])
    if not messages:
        return
    messages.sort(key=lambda item: item.message_id)
    try:
        _handle_receipt_album(messages)
    except Exception:
        logger.exception("media group flush failed key=%s", key)
        try:
            anchor = messages[0]
            _set_reaction(anchor.chat.id, anchor.message_id, "👎")
        except Exception:
            pass


def _pick_album_payload(messages: list[Message]) -> tuple[bytes, str, bytes | None, Message]:
    """Choose receipt + optional ticket PDF from an album. Prefer photo receipt over documents."""
    anchor = messages[0]
    ticket_bytes: bytes | None = None
    photo_receipt: tuple[bytes, str, Message] | None = None
    doc_receipt: tuple[bytes, str, Message] | None = None

    for message in messages:
        document = message.document
        caption = _message_body(message)
        is_ticket = bool(
            document
            and _is_pdf_document(document)
            and (_looks_like_ticket_document(document, caption) or _looks_like_ticket(caption))
        )
        if is_ticket:
            data = _download_by_file_id(document.file_id)
            if data:
                ticket_bytes = ticket_bytes or data
                if caption or _peek_ticket(message.chat.id):
                    _remember_ticket(
                        message.chat.id,
                        caption or _peek_ticket(message.chat.id),
                        ticket_file_id=document.file_id,
                    )
            continue

        downloaded = _download_file(message)
        if downloaded is None:
            continue
        file_bytes, filename = downloaded
        if message.photo:
            photo_receipt = (file_bytes, filename, message)
        elif doc_receipt is None:
            doc_receipt = (file_bytes, filename, message)

    chosen = photo_receipt or doc_receipt
    if chosen is None:
        return b"", "", ticket_bytes, anchor
    file_bytes, filename, anchor = chosen
    return file_bytes, filename, ticket_bytes, anchor


@bot.message_handler(content_types=["text"])
@bot.edited_message_handler(content_types=["text"])
@bot.channel_post_handler(content_types=["text"])
def handle_text(message: Message):
    _audit(message)
    if message.text and message.text.startswith("/"):
        return
    if _skip_provider_chat(message.chat.id):
        return
    text = _collect_appeal_text(message)
    if not _looks_like_ticket(text):
        return
    _remember_ticket(message.chat.id, text, ticket_file_id=_ticket_file_id_from_message(message))


@bot.message_handler(content_types=["photo", "document"])
@bot.edited_message_handler(content_types=["photo", "document"])
@bot.channel_post_handler(content_types=["photo", "document"])
def handle_receipt(message: Message):
    try:
        _handle_receipt(message)
    except Exception:
        logger.exception("handle_receipt failed")
        try:
            _set_reaction(message.chat.id, message.message_id, "👎")
        except Exception:
            pass


def _submit_appeal(
    message: Message,
    text: str,
    file_bytes: bytes,
    filename: str,
    ticket_file_bytes: bytes | None = None,
) -> None:
    try:
        payload = backend_process_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=text,
            file_bytes=file_bytes,
            filename=filename,
            ticket_file_bytes=ticket_file_bytes,
        )
    except requests.RequestException:
        logger.exception("backend request failed")
        _set_reaction(message.chat.id, message.message_id, "👎")
        return
    _apply_outcome(message, payload, text)


def _apply_outcome(message: Message, payload: dict, appeal_text: str) -> None:
    if payload.get("skip"):
        return
    outcome = payload.get("outcome") or "rejected"
    reply_text = (payload.get("message") or "").strip()
    if outcome == "await_receipt":
        _remember_ticket(
            message.chat.id,
            appeal_text,
            ticket_file_id=_ticket_file_id_from_message(message),
        )
        _set_reaction(message.chat.id, message.message_id, "👀")
        if reply_text:
            bot.reply_to(message, reply_text)
        return
    if outcome == "duplicate":
        _clear_ticket(message.chat.id)
        _set_reaction(message.chat.id, message.message_id, "👎")
        bot.reply_to(message, reply_text or "Апелляция уже существует.")
        return
    if outcome in {"success", "pending", "partial"}:
        _clear_ticket(message.chat.id)
        if outcome == "success":
            _set_reaction(message.chat.id, message.message_id, "👍")
        else:
            _set_reaction(message.chat.id, message.message_id, "👀")
        if reply_text:
            bot.reply_to(message, reply_text)
        return
    # Rejected (often first album item / PDF without extractable ID) — keep ticket context for retry.
    if appeal_text:
        _remember_ticket(
            message.chat.id,
            appeal_text,
            ticket_file_id=_ticket_file_id_from_message(message),
        )
    _set_reaction(message.chat.id, message.message_id, "👎")
    bot.reply_to(message, reply_text or "Апелляция не принята: ID не распознан.")


def _handle_receipt_album(messages: list[Message]) -> None:
    if not messages:
        return
    chat_id = messages[0].chat.id
    if _skip_provider_chat(chat_id):
        return
    appeal_text = _collect_appeal_text_from_messages(messages, chat_id)
    file_bytes, filename, ticket_file_bytes, anchor = _pick_album_payload(messages)
    logger.info(
        "receipt album chat_id=%s messages=%s media_group=%s text=%r filename=%r has_ticket_pdf=%s",
        chat_id,
        [m.message_id for m in messages],
        getattr(messages[0], "media_group_id", None),
        (appeal_text or "")[:240],
        filename,
        bool(ticket_file_bytes),
    )
    has_id_context = bool(
        appeal_text
        or ticket_file_bytes
        or any(
            _looks_like_ticket_document(m.document, _message_body(m))
            for m in messages
            if m.document
        )
    )
    if not file_bytes and not ticket_file_bytes:
        return
    if not has_id_context:
        return
    # Ticket-only album (PDF без фото-чека) — still submit so backend can await_receipt / reject clearly.
    _submit_appeal(anchor, appeal_text, file_bytes, filename, ticket_file_bytes)


def _handle_receipt(message: Message):
    _audit(message)
    if _skip_provider_chat(message.chat.id):
        return

    if not _enqueue_media_group(message):
        # Album item buffered; flush timer will process the whole group.
        return

    appeal_text = _collect_appeal_text(message)
    logger.info(
        "receipt chat_id=%s message_id=%s media_group=%s text=%r",
        message.chat.id,
        message.message_id,
        getattr(message, "media_group_id", None),
        (appeal_text or "")[:240],
    )

    downloaded = _download_file(message)
    file_bytes, filename = (b"", "")
    if downloaded is not None:
        file_bytes, filename = downloaded

    current_file_id = _file_id_of(message)
    ticket_file_bytes = _download_ticket_pdf(message, current_file_id)
    current_is_ticket = _looks_like_ticket_document(message.document, _message_body(message))
    has_id_context = bool(
        _message_body(message)
        or _message_body(getattr(message, "reply_to_message", None))
        or _peek_ticket(message.chat.id)
        or ticket_file_bytes
        or current_is_ticket
        or looks_like_ticket(filename)
    )
    if not file_bytes and not ticket_file_bytes:
        return
    if not has_id_context:
        return

    # When the only attachment is a ticket PDF, still forward it as ticket_file for ID mining.
    if not file_bytes and ticket_file_bytes:
        _submit_appeal(message, appeal_text, b"", "", ticket_file_bytes)
        return
    if current_is_ticket and file_bytes and not ticket_file_bytes:
        ticket_file_bytes = file_bytes
        # Keep file_bytes too — backend classifies ticket vs receipt from content/name.

    _submit_appeal(message, appeal_text, file_bytes, filename, ticket_file_bytes)


if __name__ == "__main__":
    if not TELEBOT_TOKEN:
        raise SystemExit("TELEBOT_TOKEN is not set")
    if not TGBOT_TOKEN:
        logger.warning("TGBOT_TOKEN is empty — API calls will fail")
    logger.info("Appeal bot starting, backend=%s", BACKEND_URL)
    bot.infinity_polling(
        timeout=30,
        long_polling_timeout=30,
        allowed_updates=["message", "edited_message", "channel_post", "edited_channel_post"],
    )
