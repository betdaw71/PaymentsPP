import os
import re

import requests
import telebot
from telebot.types import Message

BACKEND_URL = os.getenv("BACKEND_URL", "http://app:8080/api/v1/bot/appeals")
TGBOT_TOKEN = os.getenv("TGBOT_TOKEN", "")
TELEBOT_TOKEN = os.getenv("TELEBOT_TOKEN", "")

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

bot = telebot.TeleBot(TELEBOT_TOKEN)

HEADERS = {"Authorization": f"Token {TGBOT_TOKEN}"}


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
    payload = response.json()
    return payload.get("ok", False), payload.get("message", "Ошибка API")


def backend_process_message(chat_id: int, message_id: int, text: str, file_bytes: bytes, filename: str) -> tuple[bool, str, bool]:
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
    payload = response.json()
    skip = payload.get("skip", False)
    return payload.get("ok", False), payload.get("message", ""), skip


@bot.message_handler(commands=["start", "help"])
def help_command(message: Message):
    bot.reply_to(
        message,
        "Бот апелляций AvaPay.\n\n"
        "В группе мерчанта: /init <uuid контрагента>\n"
        "Затем отправьте сообщение с чеком (фото или файл) и ID заявки в тексте.",
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
    downloaded = _download_file(message)
    if downloaded is None:
        bot.reply_to(message, "Прикрепите чек как фото или файл (изображение/PDF).")
        return

    file_bytes, filename = downloaded
    ok, reply, skip = backend_process_message(
        chat_id=message.chat.id,
        message_id=message.message_id,
        text=message.caption or message.text or "",
        file_bytes=file_bytes,
        filename=filename,
    )
    if skip:
        return
    bot.reply_to(message, reply)


if __name__ == "__main__":
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
