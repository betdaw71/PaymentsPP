from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from basics.permissions import TraderPermission, DebugPermission, MerchantPermission, SupportPermission, \
    HeadSupportPermission, TraderDevicePermission, TgBotPermission
from sms.models import TraderDevice
from rest_framework.authtoken.models import Token
from sms.utils import process_sms_data, process_liveness
from django.db import transaction
from sms.models import SMS
from basics.models import Trader, PaymentDetailsGroup


@api_view(['POST'])
@permission_classes([TraderDevicePermission | DebugPermission])
@transaction.atomic
def process_sms(request, *args, **kwargs):

    trader_device = request.user.traderdevice.get()

    data = request.data
    success = process_sms_data(trader_device.trader, data)
    return Response(status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([TraderDevicePermission | DebugPermission])
@transaction.atomic
def liveness(request, *args, **kwargs):

    trader_device = request.user.traderdevice.get()

    data = request.data
    success = process_liveness(trader_device.trader, data)
    return Response(status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([TraderPermission | MerchantPermission | SupportPermission | HeadSupportPermission])
def get_filters_sms(request, *args, **kwargs):
    user = request.user
    data = {}

    if hasattr(user, 'trader'):
        data["status"] = [{"name": "Success", "value": 'success'}, {"name": "Pending", "value": 'pending'}, {"name": "Not Found", "value": 'not-found'}, {"name": "Wrong State", "value": 'wrong-state'}, {"name": "Red Block", "value": 'red-block'}, {"name": "FZ Block", "value": 'fz-block'}, {"name": "Compromise Block", "value": 'compr-block'}]

        if user.trader.is_boss:
            traders = Trader.objects.filter(team=user.trader.team).distinct()
            data["traders"] = [{"name": trader.user.username} for trader in traders]

    if hasattr(user, 'supportmember'):
        data["status"] = [{"name": "Success", "value": 'success'}, {"name": "Pending", "value": 'pending'}, {"name": "Not Found", "value": 'not-found'}, {"name": "Wrong State", "value": 'wrong-state'}, {"name": "Red Block", "value": 'red-block'}, {"name": "FZ Block", "value": 'fz-block'}, {"name": "Compromise Block", "value": 'compr-block'}]
        teams = user.supportmember.controlled_teams.all()
        data["teams"] = [{"name": team.name} for team in teams]
        traders = Trader.objects.filter(team__in=teams)
        data["traders"] = [{"name": trader.user.username} for trader in traders]

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([TraderPermission])
def get_sms_bot_owners(request, *args, **kwargs):
    trader_username = request.query_params.get('username')
    trader = Trader.objects.filter(telegram=trader_username)
    if not trader.exists():
        return Response(status=status.HTTP_403_FORBIDDEN)

    trader = trader.first()

    payment_details = PaymentDetailsGroup.objects.filter(trader=trader, status=1)

    data = {}

    for pd in payment_details.iterator():
        data[pd.owner] = str(pd.id)

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([TgBotPermission])
def get_sms_bot_data(request, *args, **kwargs):
    trader_username = request.query_params.get('username')
    trader = Trader.objects.filter(telegram=trader_username)
    if not trader.exists():
        return Response(status=status.HTTP_403_FORBIDDEN)

    trader = trader.first()

    group = request.query_params.get('group')

    device = TraderDevice.objects.get(trader=trader)

    device_token = Token.objects.get(user=device.user)

    headers = {"Authorization": f"Bearer {device_token}"}

    params = {
        "group": group,
        "text": "%text%",
        "from_number": "%fromNumber%",
        "received_at": "%receivedAt%",
    }

    data = {"headers": headers, "params": params}

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_blocks(request, *args, **kwargs):
    block_types = ['red-block', 'fz-block', 'compr-block']
    block_names = ['Красный блок', 'ФЗ', 'Компромат']
    data = []
    last_2_hours = timezone.now() - timedelta(hours=2)
    for block_type, block_name in zip(block_types, block_names):
        block_count = SMS.objects.filter(date__gt=last_2_hours, status=block_type).count()
        data.append({"type": block_name, "count": block_count})

    return Response(status=status.HTTP_200_OK, data=data)
