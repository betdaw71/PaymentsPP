import logging
import os
import re
import time

import requests
import telebot
from telebot.types import Message, ReactionTypeEmoji

BACKEND_URL = os.getenv("BACKEND_URL", "http://app:8080/api/v1/bot/appeals")
TGBOT_TOKEN = os.getenv("TGBOT_TOKEN", "")
TELEBOT_TOKEN = os.getenv("TELEBOT_TOKEN", "")

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
TICKET_HINT_RE = re.compile(
    r"(тикет\s*[#№n]?\s*[:：]?\s*[0-9a-fA-F]{8}|заказ\s*[:：]|id\s*заказа|номер заказа|"
    r"реквизиты из заявки|маска юзера|номер в [пг]?пс|order\s*id\s*[:：])",
    re.IGNORECASE,
)
RECEIPT_EXTS = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif")
TICKET_NAME_HINTS = ("melbet", "мелбет", "ticket", "тикет", "avapay")
PENDING_TICKET_TTL_SEC = 15 * 60
_PENDING_TICKETS: dict[int, dict] = {}
_SEEN_MEDIA_GROUPS: dict[str, float] = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("appealbot")

bot = telebot.TeleBot(TELEBOT_TOKEN)

HEADERS = {"Authorization": f"Token {TGBOT_TOKEN}"}
CHAT_ROLE_TTL_SEC = 5 * 60
_CHAT_ROLES: dict[int, tuple[str, float]] = {}

HELP_TEXT = (
    "Бот апелляций.\n\n"
    "Telegram не отдаёт ботам сообщения других ботов. "
    "Тикет сам по себе бот не увидит — нужен ответ человека или /appeal.\n\n"
    "Как обработать заявку:\n"
    "1. Ответьте на тикет чеком (фото квитанции из банка)\n"
    "2. Или ответьте на тикет командой /appeal, затем пришлите чек\n\n"
    "В BotFather отключите Group Privacy, иначе бот не видит фото в группе.\n"
    "Регистрация чата: /init <uuid контрагента>"
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


def _is_merchant_chat(chat_id: int) -> bool:
    role = backend_chat_role(chat_id)
    if role == "merchant":
        return True
    logger.info("ignore inbound chat_id=%s role=%s", chat_id, role)
    return False


def backend_process_message(
    chat_id: int,
    message_id: int,
    text: str,
    file_bytes: bytes,
    filename: str,
    ticket_file_bytes: bytes | None = None,
) -> dict:
    files = {"file": (filename, file_bytes)}
    if ticket_file_bytes:
        files["ticket_file"] = ("ticket.pdf", ticket_file_bytes)
    data = {
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "text": text or "",
    }
    response = requests.post(
        f"{BACKEND_URL}/process_message/",
        data=data,
        files=files,
        headers=HEADERS,
        timeout=60,
    )
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
    if not _is_merchant_chat(message.chat.id):
        return
    bot.reply_to(message, HELP_TEXT)


@bot.message_handler(commands=["init"])
@bot.channel_post_handler(commands=["init"])
def init_command(message: Message):
    _audit(message)
    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "Использование: /init <uuid контрагента>")
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
    bot.reply_to(message, reply)


@bot.message_handler(commands=["appeal"])
@bot.channel_post_handler(commands=["appeal"])
def appeal_command(message: Message):
    """Bind a ticket that our bot never received (other bots' messages are invisible)."""
    _audit(message)
    if not _is_merchant_chat(message.chat.id):
        return
    reply = getattr(message, "reply_to_message", None)
    ticket_text = _collect_appeal_text(message)
    ticket_file_id = _ticket_file_id_from_message(message)
    if reply is None and not _looks_like_ticket(ticket_text) and not ticket_file_id:
        bot.reply_to(
            message,
            "Ответьте командой /appeal на тикет, затем пришлите чек. "
            "Либо сразу ответьте на тикет фото квитанции из банка.",
        )
        return
    if not _looks_like_ticket(ticket_text) and not ticket_file_id:
        bot.reply_to(
            message,
            "В сообщении, на которое вы отвечаете, нет ID заявки (Заказ / Тикет / UUID).",
        )
        return
    _remember_ticket(message.chat.id, ticket_text, ticket_file_id=ticket_file_id)
    bot.reply_to(
        message,
        "Тикет принят. Пришлите чек (фото квитанции из банка) — можно следующим сообщением.",
    )


def _is_pdf_document(document) -> bool:
    if document is None:
        return False
    mime = (document.mime_type or "").lower()
    name = (document.file_name or "").lower()
    if mime in ("application/pdf", "application/x-pdf"):
        return True
    if name.endswith(".pdf"):
        return True
    if mime in ("application/octet-stream", "binary/octet-stream", "") and name.endswith(".pdf"):
        return True
    return False


def _is_receipt_document(document) -> bool:
    if document is None:
        return False
    mime = (document.mime_type or "").lower()
    name = (document.file_name or "").lower()
    if mime.startswith("image/") or mime in ("application/pdf", "application/x-pdf"):
        return True
    if mime in ("application/octet-stream", "binary/octet-stream", ""):
        return name.endswith(RECEIPT_EXTS)
    return name.endswith(RECEIPT_EXTS)


def _filename_looks_like_ticket(name: str | None) -> bool:
    lowered = (name or "").lower()
    return any(hint in lowered for hint in TICKET_NAME_HINTS)


def _looks_like_ticket_document(document, caption: str | None) -> bool:
    if document is None:
        return False
    if _filename_looks_like_ticket(getattr(document, "file_name", None)):
        return True
    if _is_pdf_document(document) and _looks_like_ticket(caption or ""):
        return True
    return False


def _generic_receipt_name(filename: str | None, content: bytes) -> str:
    if content.startswith(b"\xff\xd8\xff"):
        return "receipt.jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "receipt.png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "receipt.webp"
    if content.startswith(b"%PDF"):
        return "receipt.pdf"
    if content.startswith(b"GIF8"):
        return "receipt.gif"
    name = (filename or "").lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".heic", ".heif"):
        if name.endswith(ext):
            if ext in {".jpeg", ".heic", ".heif"}:
                return "receipt.jpg"
            return f"receipt{ext}"
    return "receipt.bin"


def _download_by_file_id(file_id: str) -> bytes | None:
    try:
        file_info = bot.get_file(file_id)
        return bot.download_file(file_info.file_path)
    except Exception:
        logger.warning("download file_id=%s failed", file_id, exc_info=True)
        return None


def _download_file(message: Message | None) -> tuple[bytes, str] | None:
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
        return content, _generic_receipt_name(document.file_name, content)

    return None


def _looks_like_ticket(text: str) -> bool:
    if not text:
        return False
    if UUID_RE.search(text):
        return True
    return bool(TICKET_HINT_RE.search(text))


def _remember_ticket(chat_id: int, text: str, ticket_file_id: str | None = None) -> None:
    prev = _PENDING_TICKETS.get(chat_id) or {}
    file_id = ticket_file_id or prev.get("ticket_file_id")
    _PENDING_TICKETS[chat_id] = {
        "text": text or prev.get("text") or "",
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


def _claim_media_group(chat_id: int, media_group_id: str | None) -> bool:
    """Process only the first item of a Telegram album."""
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


def _collect_appeal_text(message: Message) -> str:
    parts = []
    own = _message_body(message)
    if own:
        parts.append(own)
    reply = _message_body(getattr(message, "reply_to_message", None))
    if reply and reply not in parts:
        parts.append(reply)
    combined = "\n".join(parts)
    if not _looks_like_ticket(combined):
        pending = _peek_ticket(message.chat.id)
        if pending and pending not in parts:
            parts.append(pending)
            combined = "\n".join(parts)
    return combined


def _download_ticket_pdf(message: Message, receipt_file_id: str | None) -> bytes | None:
    file_id = _ticket_file_id_from_message(message)
    if not file_id or file_id == receipt_file_id:
        file_id = _peek_ticket_file_id(message.chat.id) or None
    if not file_id or file_id == receipt_file_id:
        return None
    return _download_by_file_id(file_id)


@bot.message_handler(content_types=["text"])
@bot.channel_post_handler(content_types=["text"])
def handle_text(message: Message):
    _audit(message)
    if message.text and message.text.startswith("/"):
        return
    if not _is_merchant_chat(message.chat.id):
        return
    text = _collect_appeal_text(message)
    if not _looks_like_ticket(text):
        return
    _remember_ticket(message.chat.id, text, ticket_file_id=_ticket_file_id_from_message(message))
    bot.reply_to(
        message,
        "Тикет распознан. Прикрепите чек (фото квитанции из банка) ответом на тикет.",
    )


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
            bot.reply_to(message, "Отклонена: внутренняя ошибка бота")
        except Exception:
            pass


def _handle_receipt(message: Message):
    _audit(message)
    if not _is_merchant_chat(message.chat.id):
        return
    appeal_text = _collect_appeal_text(message)
    logger.info(
        "receipt chat_id=%s message_id=%s media_group=%s text=%r",
        message.chat.id,
        message.message_id,
        getattr(message, "media_group_id", None),
        (appeal_text or "")[:240],
    )

    if not _claim_media_group(message.chat.id, getattr(message, "media_group_id", None)):
        logger.info(
            "skip extra album item chat_id=%s media_group=%s",
            message.chat.id,
            message.media_group_id,
        )
        return

    downloaded = _download_file(message)
    if downloaded is None:
        bot.reply_to(message, "Прикрепите чек как фото или файл (изображение/PDF).")
        return

    file_bytes, filename = downloaded
    current_file_id = None
    if message.document:
        current_file_id = message.document.file_id
    elif message.photo:
        current_file_id = message.photo[-1].file_id

    ticket_file_bytes = _download_ticket_pdf(message, current_file_id)
    current_is_ticket = _looks_like_ticket_document(message.document, _message_body(message))

    if not _looks_like_ticket(appeal_text) and not ticket_file_bytes and not current_is_ticket:
        bot.reply_to(
            message,
            "Не вижу ID заявки. Ответьте чеком на тикет "
            "или сначала /appeal ответом на тикет, затем пришлите чек.",
        )
        return

    try:
        payload = backend_process_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=appeal_text,
            file_bytes=file_bytes,
            filename=filename,
            ticket_file_bytes=ticket_file_bytes,
        )
    except requests.RequestException as exc:
        logger.exception("backend request failed")
        _set_reaction(message.chat.id, message.message_id, "👎")
        bot.reply_to(message, f"Отклонена: нет связи с API ({exc})")
        return

    if payload.get("skip"):
        return

    outcome = payload.get("outcome") or "rejected"
    reply_text = payload.get("message") or ""

    if outcome == "await_receipt":
        _remember_ticket(
            message.chat.id,
            appeal_text,
            ticket_file_id=_ticket_file_id_from_message(message) or current_file_id,
        )
        bot.reply_to(
            message,
            reply_text
            or "Тикет распознан. Пришлите чек (фото квитанции из банка).",
        )
        return

    if payload.get("recognized") or payload.get("ok"):
        _clear_ticket(message.chat.id)

    recognized = bool(payload.get("recognized"))
    if recognized:
        _set_reaction(message.chat.id, message.message_id, "👀")

    if outcome == "success":
        _set_reaction(message.chat.id, message.message_id, "👍")
        bot.reply_to(message, reply_text or "Успех")
    elif outcome == "pending":
        bot.reply_to(message, reply_text or "Апелляция принята, ожидаем подтверждения.")
    elif outcome == "partial":
        bot.reply_to(message, reply_text)
    else:
        _set_reaction(message.chat.id, message.message_id, "👎")
        bot.reply_to(message, reply_text or "Отклонена")


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
