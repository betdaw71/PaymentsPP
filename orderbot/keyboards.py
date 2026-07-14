from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
import telebot
import json

from backend_connector import backend_get_rejection_reasons, backend_get_owners


def keyboard_reasons(order_id, payment_system, username):
    keyboard = InlineKeyboardMarkup()
    success, reasons = backend_get_rejection_reasons(username, payment_system)
    print(reasons)
    for reason in reasons:
        keyboard.add(InlineKeyboardButton(text=reason['text'], callback_data=f"dec/{order_id}/{reason['name']}"))

    return keyboard


def keyboard_decide(order_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="Выполнено", callback_data=f"done/{order_id}"))
    keyboard.add(InlineKeyboardButton(text="Отклонить", callback_data=f"decline/{order_id}"))
    return keyboard


def keyboard_continue(group):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="Следующий ордер", callback_data=f"owner/{group}"))
    keyboard.add(InlineKeyboardButton(text="Сменить ЛК", callback_data=f"change/{group}"))
    return keyboard


def keyboard_change_pa(group):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="Сменить ЛК", callback_data=f"change/{group}"))
    return keyboard


def keyboards_owners(username):
    keyboard = InlineKeyboardMarkup()
    success, owners = backend_get_owners(username)

    for owner in owners:
        keyboard.add(InlineKeyboardButton(text=owner['name'], callback_data=f"owner/{owner['id']}"))

    return keyboard

