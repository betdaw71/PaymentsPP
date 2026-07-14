from utils import get_rejection_texts


def get_user_not_exists():
    return "Такого пользователя не существует"


def get_welcome(name):
    return f"{name}, приветствую!"


def get_pd_text(pd):
    txt = ""
    for key in pd.keys():
        txt += f"{key}: `{pd[key]}`" + "\n"
    return txt


def get_order_text(order):
    receiver = order['destination_details']['card_number'] if order['payment_system'] == 'Sber' else order['destination_details']['phone']
    bank = order['destination_details']['bank'] if order['payment_system'] == 'SBP' else 'Сбербанк'
    transfer_type = 'Card' if order['payment_system'] == 'Sber' else order['payment_system']
    owner = order['destination_details'].get('owner', '--')
    sender = order['payment_details']['card_number'] if order['payment_system'] == 'Sber' else order['payment_details']['phone']

    txt = f"<b>Новая выплата</b>\n\n"
    txt += f"ID: {order['id'][:8]}\n"
    txt += f"Сумма: <code>{str(order['amount'])}</code>\n"
    txt += f"Получатель: <code>{receiver}</code>\n"
    txt += f"Банк: <code>{bank}</code>\n"
    txt += f"Тип: <code>{transfer_type}</code>\n"
    txt += f"ФИО: <code>{owner}</code>\n\n"
    txt += f"ЛК для осуществления выплаты:\n{order['owner']}\n\n"
    txt += f"Реквизиты для осуществления выплаты:\n{sender}"
    return txt


# ID: 6741570
# Сумма: 30000.00
# Получатель: * * * * * * * * * *
# Банк: Сбербанк
# Тип: Card
# ФИО: —
#
# ЛК для осуществления выплаты:
# Иванов Иван Иванович
#
# def get_order_text(order):
#     txt = f"*Новая выплата*\n\n"
#     txt += f"{order['payment_system']}, `{order['amount']}` {order['currency']}" + "\n"
#     txt += f"ID: `{order['id']}`\n"
#     txt += f"Сумма: `{str(order['amount'])}`\n"
#     txt += f"Получатель: `{get_pd_text(order['destination_details'])}`\n"
#     txt += f"ФИО: `{order['owner']}`" + "\n"
#     txt += f"От:\n {get_pd_text(order['payment_details'])}"
#     txt += f"Куда:\n {get_pd_text(order['destination_details'])}"
#     return txt


def get_send_doc_text():
    return "Пришлите pdf-документ"


def get_choose_reason_text():
    return "Выберите причину отказа"


def get_success_text():
    return "Успешно"


def get_stopped_text():
    return "Остановлено"


def get_choose_owner():
    return "Выберите ЛК"

def get_no_orders_text():
    return "Для данного ЛК нет активных ордеров"

def get_wrong_rejection_text():
    return f"Неверная команда. Возможные варианты: {get_rejection_texts()}"


order = {"id": "494994", "amount": 1000, "currency": "RUB", "payment_system": "Sber", "owner": "Иванов ИИ", "expires_at": 129244, "payment_details": {"deposit_number": "5428"}, "destination_details": {"card_number": "0000111122229112"},}

# print(get_order_text(order))
