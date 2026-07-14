import json


def get_user_not_exists():
    return "Такого пользователя не существует"


def get_welcome(name):
    return f"{name}, приветствую!"


def form_emergency_msg(block_type: str, owner: str, sms_text: str):
    if block_type == "compr-block":
        block_word = "Компрометация"
    elif block_type == "fz-block":
        block_word = "Блок по ФЗ"
    elif block_type == "red-block":
        block_word = "Красный блок"
    else:
        block_word = "Блокировка"

    text = f"*{block_word}*\n\n"
    text += f"ЛК: {owner}\n\nТекст СМС:\n{sms_text}"

    return text


