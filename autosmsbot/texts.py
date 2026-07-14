import json

from utils import get_rejection_texts


def get_user_not_exists():
    return "Такого пользователя не существует"


def get_welcome(name):
    return f"{name}, приветствую!"


def get_choose_owner():
    return "Выберите ЛК"


def get_text_from_sms_data(data):
    texts = []
    texts.append("Token\n\n" + f'```{data.get("token")}```')
    texts.append("Group\n\n" + f'```{data.get("group")}```')
    return texts
