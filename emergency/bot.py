import time
import logging
import sys
import telebot
from backend_connector import *
from texts import *
from telebot.types import Message, CallbackQuery
import os
import dotenv

dotenv.load_dotenv()

TELEBOT_TOKEN = os.getenv('TELEBOT_TOKEN')
bot = telebot.TeleBot(TELEBOT_TOKEN)


@bot.message_handler(commands=['start'])
def start(message: Message):
    username = message.from_user.username
    user_id = message.from_user.id
    success, name = backend_check_user(username, user_id)

    if not success:
        bot.send_message(user_id, get_user_not_exists())
        return

    bot.send_message(user_id, get_welcome(name))


def send_emergency(block_type: str, owner: str, text: str, user_id: int):
    bot.send_message(user_id, form_emergency_msg(block_type, owner, text), parse_mode="Markdown")


if __name__ == "__main__":
    while True:
        try:
            bot.polling(none_stop=True, timeout=30)
        except:
            logging.error("error: {}".format(sys.exc_info()))
            time.sleep(2)