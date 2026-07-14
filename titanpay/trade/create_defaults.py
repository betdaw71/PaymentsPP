import uuid
from basics.models import TrafficType, Currency, Language, Balance, Trader, PaymentSystem
from merchant.models import Merchant
from trade.models import TransactionType, InOrderStatus, OutOrderStatus, Address, InOrder, OutOrder
from payments.models import PayInStatus, PayOutStatus, PayIn, PayOut
from bots.models import TGBot
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token


def create_pay_in_statuses():
    for name in ["New", "In Progress", "Success", "Failed"]:
        if not PayInStatus.objects.filter(name=name).exists():
            PayInStatus.objects.create(name=name)


def create_pay_out_statuses():
    for name in ["New", "In Progress", "Success", "Failed"]:
        if not PayOutStatus.objects.filter(name=name).exists():
            PayOutStatus.objects.create(name=name)


def create_inorder_statuses():
    for name in ["New", "Money sent by user", "Expired", "Cancelled", "Arbitrage", "Completed", "Cancelled by support", "Cannot process", "Cancelled by trader"]:
        if not InOrderStatus.objects.filter(name=name).exists():
            InOrderStatus.objects.create(name=name)


def create_outorder_statuses():
    for name in ["New", "Money sent by trader", "Expired", "Cancelled", "Arbitrage", "Completed", "Cancelled by support", "Cannot process", 'Failed', 'Manual check']:
        if not OutOrderStatus.objects.filter(name=name).exists():
            OutOrderStatus.objects.create(name=name)


def create_transaction_types():
    for name in ["Charge", "Deposit", "Freeze", "Withdrawal", "Transfer"]:
        if not TransactionType.objects.filter(name=name).exists():
            TransactionType.objects.create(name=name)


def create_balances():
    for _type in [2, 3]:
        if not Balance.objects.filter(type=_type).exists():
            Balance.objects.create(type=_type)


def create_currencies():
    if not Currency.objects.filter(symbol="RUB").exists():
        Currency.objects.create(name="Ruble", symbol="RUB")


def create_languages():
    if not Language.objects.filter(name="Russian").exists():
        Language.objects.create(name="Russian")


def create_tgbots():
    if not User.objects.filter(username="outorder_bot_user").exists():
        outorder_user = User.objects.create_user(username="outorder_bot_user", password=str(uuid.uuid4()))
        TGBot.objects.create(user=outorder_user)
        Token.objects.create(user=outorder_user)

    if not User.objects.filter(username="smsdata_bot_user").exists():
        smsdata_user = User.objects.create_user(username="smsdata_bot_user", password=str(uuid.uuid4()))
        TGBot.objects.create(user=smsdata_user)
        Token.objects.create(user=smsdata_user)


def create_defaults():
    create_currencies()
    create_languages()
    create_balances()
    create_transaction_types()
    create_inorder_statuses()
    create_pay_in_statuses()
    create_pay_out_statuses()
    create_outorder_statuses()
    create_tgbots()
