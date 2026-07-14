from decimal import Decimal
import requests
from django.utils import timezone

from titanpay.settings import EMERGENCY_URL
from basics.models import PaymentDetails, PaymentSystem, Trader, PaymentDetailsGroup
from trade.models import InOrder, OutOrder, InOrderStatus
from sms.models import SMS


def send_alert(block_type: str, owner: str, text: str, user_id: int):
    url = EMERGENCY_URL + '/alert/'

    data = {
        "block_type": block_type,
        "owner": owner,
        "text": text,
        "user_id": user_id
    }
    headers = {'Content-Type': 'application/json'}
    try:
        r = requests.post(url, json=data, headers=headers)
    except:
        pass


def truncate_text(text):
    if len(text) > 255:
        return text[:255]
    return text


def process_liveness(trader, data):
    groups = PaymentDetailsGroup.objects.filter(id=data['group'])
    if not groups.exists():
        return False

    group = groups.first()

    if group.trader != trader:
        return False

    group.auto_live = timezone.now()
    group.save()


def process_sms_data(trader, data):

    if not data["success"] and data.get("text") is None:
        return False

    text = truncate_text(data['text'])
    groups = PaymentDetailsGroup.objects.filter(id=data['group'])

    if not groups.exists():
        return False

    group = groups.first()

    if group.trader != trader:
        return False

    if not data["success"]:
        SMS.objects.create(status='not-found', text=text, device=group)
        return True

    if data['blocked']:
        SMS.objects.create(status=data["block_type"], text=text, device=group)
        group.status = 5
        group.save()
        send_alert(block_type=data["block_type"], owner=group.owner, text=text, user_id=group.trader.telegram_user_id)
        return True

    if 'deposit_number' in data.keys():
        details = PaymentDetails.objects.filter(deposit_number__endswith=data['deposit_number'], group=group, status=1)
    elif 'card_number' in data.keys():
        details = PaymentDetails.objects.filter(card_number__endswith=data['card_number'], group=group, status=1)
    else:
        SMS.objects.create(status='not-found', text=text, device=group)
        return True

    if not details.exists():
        SMS.objects.create(status='not-found', text=text, device=group)
        return True

    if data['direction'] == 'in':
        orders = InOrder.objects.filter(solution__payment_system__name__in=data['methods'], payment_details=details.first(), amount=Decimal(data['amount']))

        ongoing_orders = orders.filter(status__name__in=["New", "Money sent by user"])

        if ongoing_orders.exists():
            order: InOrder = ongoing_orders.select_for_update().first()
            sms = SMS.objects.create(status='success', text=text, device=group)
            order.automatically_complete(sms=sms, balance=data.get('balance', None))
            return True
        else:
            arbitrage_orders = orders.filter(status__name="Arbitrage")

            if not arbitrage_orders.exists():
                SMS.objects.create(status='not-found', text=text, device=group)
                return True

            sms = SMS.objects.create(status='success', text=text, device=group)
            order: InOrder = arbitrage_orders.select_for_update().first()
            order.automatically_complete_arbitrage(sms=sms, balance=data.get('balance', None))
            return True

    else:
        orders = OutOrder.objects.filter(solution__payment_system__name__in=data['methods'], payment_details=details.first(), amount=Decimal(data['amount']))

        ongoing_orders = orders.filter(status__name__in=["Money sent by trader", "New"], sms_sent=False)

        if ongoing_orders.exists():
            order: OutOrder = ongoing_orders.select_for_update().first()
            sms = SMS.objects.create(status='success', text=text, device=group)
            order.auto_sms(sms=sms, balance=data.get('balance', None))
            return True
        else:
            SMS.objects.create(status='not-found', text=text, device=group)
            return True

    return True
