import asyncio
import time
import telebot

from autochecker_connector import send_to_fastapi
from backend_connector import *
from keyboards import keyboard_reasons, keyboards_owners, keyboard_decide, keyboard_continue, keyboard_change_pa
from texts import *
from telebot.types import Message, ForceReply, CallbackQuery
import os
import dotenv

from utils import get_rejection_texts, get_stop_texts

TELEBOT_TOKEN = os.getenv('TELEBOT_TOKEN')
bot = telebot.TeleBot(TELEBOT_TOKEN)
# dotenv.load_dotenv()


@bot.message_handler(commands=['start'])
def start(message: Message):
    chat_id = message.from_user.id
    username = message.from_user.username
    success, name = backend_check_user(username)

    if not success:
        bot.send_message(chat_id, get_user_not_exists())
        return

    bot.send_message(chat_id, get_welcome(name))


@bot.message_handler(commands=['work'])
def handle_work(message: Message):
    chat_id = message.from_user.id
    username = message.from_user.username
    keyboard = keyboards_owners(username)
    bot.send_message(chat_id, get_choose_owner(), reply_markup=keyboard)


def work(message: Message or CallbackQuery, group):
    chat_id = message.from_user.id
    username = message.from_user.username
    success, order = backend_get_order(username, group)
    print(order)
    if order:
        msg = bot.send_message(chat_id, get_order_text(order), reply_markup=keyboard_decide(order['id']), parse_mode="HTML")
    else:
        msg = bot.send_message(chat_id, get_no_orders_text(), reply_markup=keyboard_change_pa(group), parse_mode="HTML")


def handle_reply(message: Message, order: str):
    chat_id = message.from_user.id
    force_reply = ForceReply(selective=False)

    if message.document is not None:
        document = message.document

        if document.mime_type != 'application/pdf':
            msg = bot.reply_to(message, get_send_doc_text(), reply_markup=force_reply)
            bot.register_next_step_handler(msg, lambda m: handle_reply(m, order))
            return
        else:
            success, order_obj = backend_get_order(message.from_user.username, None, order)
            file_info = bot.get_file(document.file_id)
            file_bytes = bot.download_file(file_info.file_path)

            result = send_to_fastapi(order_obj, file_bytes)

            backend_send_pdf(order, result['file_url'], result['success'], result['comment'])

            bot.send_message(chat_id, get_success_text(), reply_markup=keyboard_continue(order_obj["payment_details"]["group"]))

    elif message.document is None:
        msg = bot.send_message(chat_id, get_send_doc_text(), reply_markup=force_reply)
        bot.register_next_step_handler(msg, lambda m: handle_reply(m, order))


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call: CallbackQuery) -> None:

    cd = call.data
    chat_id = call.message.chat.id
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=None)
    except Exception as e:
        pass

    parts = list(cd.split('/'))

    if "done" == parts[0]:
        msg = bot.send_message(chat_id, get_send_doc_text(), reply_markup=ForceReply())
        bot.register_next_step_handler(msg, lambda m: handle_reply(m, parts[1]))
        return

    if "decline" == parts[0]:
        username = call.from_user.username
        msg = bot.send_message(chat_id, get_choose_reason_text(), reply_markup=keyboard_reasons(parts[1], "Sber", username))
        return

    if "dec" == parts[0]:
        username = call.from_user.username
        reason = parts[2]
        backend_send_rejection_reasons(parts[1], reason)
        success, order_obj = backend_get_order(call.from_user.username, None, parts[1])
        bot.send_message(chat_id, get_success_text(), reply_markup=keyboard_continue(order_obj["payment_details"]["group"]))
        return

    if "owner" == parts[0]:
        return work(call, parts[1])

    if "change" == parts[0]:
        keyboard = keyboards_owners(call.from_user.username)
        bot.send_message(chat_id, get_choose_owner(), reply_markup=keyboard)
        return

    order_id, reason = parts[0], parts[1]
    group_id = backend_send_rejection_reasons(order_id, reason)
    bot.send_message(chat_id, get_success_text())
    return work(call, group_id)


if __name__ == "__main__":
    while True:
        # try:
            bot.polling(none_stop=True, timeout=30)
        # except:
        #     logging.error("error: {}".format(sys.exc_info()))
        #     time.sleep(2)