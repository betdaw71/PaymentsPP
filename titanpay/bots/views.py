from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from rest_framework.response import Response
from basics.permissions import TraderPermission, DebugPermission, MerchantPermission, SupportPermission, \
    HeadSupportPermission, TraderDevicePermission, TgBotPermission
from bots.serializers import OutOrderBotSerializer
from sms.models import TraderDevice
from rest_framework.authtoken.models import Token
from sms.utils import process_sms_data
from django.db import transaction
from basics.models import Trader, PaymentDetailsGroup
from trade.models import OutOrder
from titanpay.settings import SMS_ENDPOINT


@api_view(['GET'])
@permission_classes([TgBotPermission])
def check_user(request, *args, **kwargs):
    trader_username = request.query_params.get('username')
    trader = Trader.objects.filter(telegram=trader_username)
    if not trader.exists():
        return Response(status=status.HTTP_403_FORBIDDEN)

    trader = trader.first()

    return Response(status=status.HTTP_200_OK, data={"name": trader.user.first_name})


@api_view(['GET'])
@permission_classes([TgBotPermission])
def get_sms_bot_owners(request, *args, **kwargs):
    trader_username = request.query_params.get('username')
    trader = Trader.objects.filter(telegram=trader_username)
    if not trader.exists():
        return Response(status=status.HTTP_403_FORBIDDEN)

    trader = trader.first()

    payment_details = PaymentDetailsGroup.objects.filter(trader=trader, status=1)

    data = []

    for pd in payment_details.iterator():
        data.append({"name": pd.owner, "id": str(pd.id)})

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

    data = {"group": str(group), "token": str(device_token)}

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([TgBotPermission])
def get_next_outorder(request, *args, **kwargs):
    trader_username = request.query_params.get('username')

    trader = Trader.objects.filter(telegram=trader_username)

    if not trader.exists():
        return Response(status=status.HTTP_403_FORBIDDEN)

    trader = trader.first()

    order_id = request.query_params.get('order')

    if order_id is not None:
        order = OutOrder.objects.get(id=order_id)
        serializer = OutOrderBotSerializer(order)
        return Response(status=status.HTTP_200_OK, data=serializer.data)

    group_id = request.query_params.get('group')

    group_obj = PaymentDetailsGroup.objects.get(id=group_id)

    out_orders = OutOrder.objects.filter(payment_details__group=group_obj, status__name="New").order_by('creation_date')

    if not out_orders.exists():
        return Response(status=status.HTTP_200_OK, data={})

    order = out_orders.first()

    serializer = OutOrderBotSerializer(order)

    return Response(status=status.HTTP_200_OK, data=serializer.data)


@api_view(['GET'])
@permission_classes([TgBotPermission])
def get_rejection_reasons(request, *args, **kwargs):
    trader_username = request.query_params.get('username')

    trader = Trader.objects.filter(telegram=trader_username)

    if not trader.exists():
        return Response(status=status.HTTP_403_FORBIDDEN)

    data = OutOrder.REJECTION_CHOICES
    return Response(status=status.HTTP_200_OK, data=data)


@transaction.atomic
@api_view(['POST'])
@permission_classes([TgBotPermission])
def reject(request, *args, **kwargs):
    order_id = request.data.get('order_id')
    reason = request.data.get('reason')

    out_order = OutOrder.objects.get(id=order_id)
    out_order.cannot_process(reason=reason)

    return Response(status=status.HTTP_200_OK)


@transaction.atomic
@api_view(['POST'])
@permission_classes([TgBotPermission])
def check_user_emergency(request, *args, **kwargs):
    username = request.data.get('username')
    user_id = request.data.get('user_id')

    trader = Trader.objects.filter(telegram=username)

    if not trader.exists():
        return Response(status=status.HTTP_403_FORBIDDEN)

    trader = trader.first()
    trader.telegram_user_id = user_id
    trader.save()
    return Response(status=status.HTTP_200_OK, data={'name': trader.user.first_name})


@transaction.atomic
@api_view(['POST'])
@permission_classes([TgBotPermission])
def add_pdf(request, *args, **kwargs):
    order_id = request.data.get('order_id')
    url = request.data.get('url')
    success = request.data.get('success')
    comment = request.data.get('comment')

    out_order = OutOrder.objects.get(id=order_id)
    out_order.money_sent()
    out_order.add_pdf(url, success, comment)

    return Response(status=status.HTTP_200_OK)
