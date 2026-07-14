import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv('BACKEND_URL')
TGBOT_TOKEN = os.getenv('TGBOT_TOKEN')


def backend_check_user(username: str, user_id: int):
    r = requests.post(BACKEND_URL + '/check_user_emergency/', headers={"Authorization": f"Token {TGBOT_TOKEN}", "GATE": "lwkdo3di4ndRrncr4295"}, data={'username': username, 'user_id': user_id})

    if r.status_code == 200:
        return True, r.json()['name']
    return False

