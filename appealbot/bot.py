import logging
import os
import re

import requests
import telebot
from telebot.types import Message, ReactionTypeEmoji

BACKEND_URL = os.getenv("BACKEND_URL", "http://app:8080/api/v1/bot/appeals")
TGBOT_TOKEN = os.getenv("TGBOT_TOKEN", "")
TELEBOT_TOKEN = os.getenv("TELEBOT_TOKEN", "")

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("appealbot")

bot = telebot.TeleBot(TELEBOT_TOKEN)

HEADERS = {"Authorization": f"Token {TGBOT_TOKEN}"}


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


def backend_process_message(
    chat_id: int, message_id: int, text: str, file_bytes: bytes, filename: str
) -> dict:
    files = {"file": (filename, file_bytes)}
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


@bot.message_handler(commands=["start", "help"])
def help_command(message: Message):
    bot.reply_to(
        message,
        "Бот апелляций AvaPay.\n\n"
        "1. В BotFather отключите Group Privacy (иначе бот не видит фото в группе)\n"
        "2. В группе мерчанта: /init <uuid контрагента>\n"
        "3. Отправьте фото чека с ID заявки в подписи (caption)",
    )


@bot.message_handler(commands=["init"])
def init_command(message: Message):
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
    bot.reply_to(message, reply)


def _download_file(message: Message) -> tuple[bytes, str] | None:
    if message.photo:
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        content = bot.download_file(file_info.file_path)
        return content, "receipt.jpg"

    if message.document:
        document = message.document
        mime = (document.mime_type or "").lower()
        allowed = mime.startswith("image/") or mime == "application/pdf"
        if not allowed:
            return None
        file_info = bot.get_file(document.file_id)
        content = bot.download_file(file_info.file_path)
        name = document.file_name or "receipt"
        return content, name

    return None


@bot.message_handler(content_types=["text"])
def handle_text(message: Message):
    if message.text and message.text.startswith("/"):
        return
    if UUID_RE.search(message.text or ""):
        bot.reply_to(message, "Прикрепите чек (фото или файл) к сообщению с ID заявки.")


@bot.message_handler(content_types=["photo", "document"])
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
    logger.info(
        "receipt chat_id=%s message_id=%s caption=%r",
        message.chat.id,
        message.message_id,
        message.caption or "",
    )

    downloaded = _download_file(message)
    if downloaded is None:
        bot.reply_to(message, "Прикрепите чек как фото или файл (изображение/PDF).")
        return

    file_bytes, filename = downloaded
    try:
        payload = backend_process_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=message.caption or message.text or "",
            file_bytes=file_bytes,
            filename=filename,
        )
    except requests.RequestException as exc:
        logger.exception("backend request failed")
        _set_reaction(message.chat.id, message.message_id, "👎")
        bot.reply_to(message, f"Отклонена: нет связи с API ({exc})")
        return

    if payload.get("skip"):
        return

    recognized = bool(payload.get("recognized"))
    outcome = payload.get("outcome") or "rejected"
    reply_text = payload.get("message") or ""

    if recognized:
        _set_reaction(message.chat.id, message.message_id, "👀")

    if outcome == "success":
        _set_reaction(message.chat.id, message.message_id, "👍")
        bot.reply_to(message, reply_text or "Успех")
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
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
