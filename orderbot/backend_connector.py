import json
import os

import requests

BACKEND_URL = os.getenv('BACKEND_URL')
TGBOT_TOKEN = os.getenv('TGBOT_TOKEN')


def backend_check_user(username: str):
    print("HERE")
    r = requests.get(BACKEND_URL + '/check_user/', headers={"Authorization": f"Token {TGBOT_TOKEN}", "GATE": "lwkdo3di4ndRrncr4295"}, params={'username': username})
    print(r.status_code)
    print(r.text)
    if r.status_code == 200:
        return True, r.json()["name"]
    return False, "Name"


def backend_get_owners(username: str):
    r = requests.get(BACKEND_URL + '/get_sms_bot_owners/', headers={"Authorization": f"Token {TGBOT_TOKEN}", "GATE": "lwkdo3di4ndRrncr4295"},
                     params={'username': username})

    if r.status_code == 200:
        return True, r.json()
    return False, []


def backend_get_order(username: str, group: str = None, order_id=None):
    r = requests.get(BACKEND_URL + '/get_next_outorder/', headers={"Authorization": f"Token {TGBOT_TOKEN}", "GATE": "lwkdo3di4ndRrncr4295"},
                     params={'username': username, 'group': group, 'order': order_id})
    print(r.text)
    if r.status_code == 200:
        return True, r.json()
    return False, []


def backend_get_rejection_reasons(username, payment_system):
    r = requests.get(BACKEND_URL + '/get_rejection_reasons/', headers={"Authorization": f"Token {TGBOT_TOKEN}", "GATE": "lwkdo3di4ndRrncr4295"}, params={'username': username,})
    print(r.text)
    print(r.status_code)
    if r.status_code == 200:
        data = []
        for reason in r.json():
            data.append({"name": reason[0], "text": reason[1]})
        return True, data
    return False, []


def backend_send_rejection_reasons(order_id, reason):
    r = requests.post(BACKEND_URL + '/reject/', headers={"Authorization": f"Token {TGBOT_TOKEN}", "GATE": "lwkdo3di4ndRrncr4295"},
                      json={'order_id': order_id, 'reason': reason})
    print(r.text)
    if r.status_code == 200:
        return True
    return False


def backend_send_pdf(order_id, url, success, comment):
    r = requests.post(BACKEND_URL + '/add_pdf/', headers={"Authorization": f"Token {TGBOT_TOKEN}", "GATE": "lwkdo3di4ndRrncr4295"},
                     json={'order_id': order_id, 'url': url, 'success': success, 'comment': comment})
    print(r.text)
    if r.status_code == 200:
        return True
    return False


