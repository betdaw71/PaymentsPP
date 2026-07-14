import time
import logging
import sys
import telebot
from backend_connector import *
from keyboards import keyboards_owners
from texts import *
from telebot.types import Message, CallbackQuery
import os
import dotenv

dotenv.load_dotenv()

TELEBOT_TOKEN = os.getenv('TELEBOT_TOKEN')
bot = telebot.TeleBot(TELEBOT_TOKEN)


@bot.message_handler(commands=['start'])
def start(message: Message):
    chat_id = message.from_user.id
    username = message.from_user.username
    success, name = backend_check_user(username)

    if not success:
        bot.send_message(chat_id, get_user_not_exists())
        return

    bot.send_message(chat_id, get_welcome(name))


@bot.message_handler(commands=['connect'])
def handle_work(message: Message):
    chat_id = message.from_user.id
    username = message.from_user.username
    keyboard = keyboards_owners(username)
    bot.send_message(chat_id, get_choose_owner(), reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call: CallbackQuery) -> None:

    cd = call.data
    chat_id = call.message.chat.id
    username = call.from_user.username
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=None)
    except Exception as e:
        pass

    parts = list(cd.split('/'))

    if "owner" == parts[0]:
        sucess, data = backend_get_connection_data(username, parts[1])
        texts = get_text_from_sms_data(data)
        print(data.get('headers'))
        for text in texts:
            bot.send_message(chat_id, text, parse_mode="Markdown")
            time.sleep(0.7)


if __name__ == "__main__":
    while True:
        try:
            bot.polling(none_stop=True, timeout=30)
        except:
            logging.error("error: {}".format(sys.exc_info()))
            time.sleep(2)