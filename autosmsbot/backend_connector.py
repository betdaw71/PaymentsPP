import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv('BACKEND_URL')
TGBOT_TOKEN = os.getenv('TGBOT_TOKEN')


def backend_check_user(username: str):
    r = requests.get(BACKEND_URL + '/check_user/', headers={"Authorization": f"Token {TGBOT_TOKEN}", "GATE": "lwkdo3di4ndRrncr4295"}, params={'username': username})

    if r.status_code == 200:
        return True, r.json()["name"]
    return False, "Name"


def backend_get_owners(username: str):
    r = requests.get(BACKEND_URL + '/get_sms_bot_owners/', headers={"Authorization": f"Token {TGBOT_TOKEN}", "GATE": "lwkdo3di4ndRrncr4295"},
                     params={'username': username})

    if r.status_code == 200:
        return True, r.json()
    return False, []


def backend_get_connection_data(username, group):
    r = requests.get(BACKEND_URL + '/get_sms_bot_data/', headers={"Authorization": f"Token {TGBOT_TOKEN}", "GATE": "lwkdo3di4ndRrncr4295"},
                     params={'username': username, 'group': group})
    if r.status_code == 200:
        return True, r.json()
    return False, {}

