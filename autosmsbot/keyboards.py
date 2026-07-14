from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
import telebot
import json

from backend_connector import backend_get_owners


def keyboards_owners(username):
    keyboard = InlineKeyboardMarkup()
    success, owners = backend_get_owners(username)

    print(owners)

    for owner in owners:
        keyboard.add(InlineKeyboardButton(text=owner['name'], callback_data=f"owner/{owner['id']}"))

    return keyboard