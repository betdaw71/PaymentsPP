from datetime import timedelta
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.decorators import api_view, permission_classes
from basics.models import PaymentSystem, Currency, TrafficType, Trader, TraderTeam, TraderTeamRates
from rest_framework import status
from rest_framework.response import Response

from basics.permissions import HeadSupportPermission, DebugPermission
from basics.serializers import TraderTeamRatesSerializer
from merchant.models import Merchant
from trade.models import InOrderStatus, OutOrderStatus, InOrder, OutOrder
from trade.utils2 import expire, update_balances, update_pd, expire_pay_outs, update_ps
from django.utils import timezone
from django.db.models import Sum, F, Count
from django.http import JsonResponse
from django.db import transaction


@api_view(['POST'])
@permission_classes([IsAdminUser])
def update_view(request, *args, **kwargs):

    success = True
    # try:
    update_balances()
    # except Exception as e:
    #     print(e)
    #     success = False

    # try:
    update_pd()
    # except Exception as e:
    #     print(e)
    #     success = False

    # try:
    expire()
    # except Exception as e:
    #     print(e)
    #     success = False

    # try:
    # expire_pay_outs()
    # except:
    #     success = False

    # try:
    update_ps()
    # except Exception as e:
    #     print(e)
    #     success = False
    #
    # if not success:
    #     return Response(status=status.HTTP_400_BAD_REQUEST, data={"success": success})

    return Response(status=status.HTTP_200_OK, data={"success": success})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_filters_inorder(request, *args, **kwargs):
    user = request.user
    statuses = InOrderStatus.objects.all()
    traffic_types = TrafficType.objects.all()
    data = {"status": [{"name": _status.name} for _status in statuses]}

    if hasattr(user, 'merchant') or hasattr(user, 'submerchant'):
        payment_systems = PaymentSystem.objects.all()
        data["payment_system"] = [{"name": ps.name} for ps in payment_systems]

        currencies = Currency.objects.filter(paymentsystem__in=payment_systems).distinct()
        data["currencies"] = [{"name": currency.symbol} for currency in currencies]

    if hasattr(user, 'trader'):
        payment_systems = PaymentSystem.objects.filter(currency=user.trader.currency).distinct()
        data["traffic_type"] = [{"name": traffic.name} for traffic in traffic_types]
        data["payment_system"] = [{"name": ps.name} for ps in payment_systems]

        if user.trader.is_boss:
            traders = Trader.objects.filter(team=user.trader.team).distinct()
            data["traders"] = [{"name": trader.user.username} for trader in traders]

    if hasattr(user, 'teamlead'):
        payment_systems = PaymentSystem.objects.filter().distinct()
        data["traffic_type"] = [{"name": traffic.name} for traffic in traffic_types]
        data["payment_system"] = [{"name": ps.name} for ps in payment_systems]
        teams = TraderTeam.objects.filter(teamlead=user.teamlead)

        traders = Trader.objects.filter(team__in=teams).distinct()
        data["traders"] = [{"name": trader.user.username} for trader in traders]

    if hasattr(user, 'supportmember'):
        teams = user.supportmember.controlled_teams.all()
        data["teams"] = [{"name": team.name} for team in teams]
        data["traffic_type"] = [{"name": traffic.name} for traffic in traffic_types]
        traders = Trader.objects.filter(team__in=teams)
        data["traders"] = [{"name": trader.user.username} for trader in traders]

        currencies = Currency.objects.filter(trader__in=traders).distinct()
        data["currencies"] = [{"name": currency.symbol} for currency in currencies]

        payment_systems = PaymentSystem.objects.filter(currency__in=currencies).distinct()
        data["payment_system"] = [{"name": ps.name} for ps in payment_systems]

        if user.supportmember.is_head:
            merchants = Merchant.objects.all()
            data["merchants"] = [{"name": merch.user.username} for merch in merchants]

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_filters_outorder(request, *args, **kwargs):
    user = request.user
    statuses = OutOrderStatus.objects.all()
    traffic_types = TrafficType.objects.all()
    data = {"status": [{"name": _status.name} for _status in statuses]}

    if hasattr(user, 'merchant') or hasattr(user, 'submerchant'):
        payment_systems = PaymentSystem.objects.all()
        data["payment_system"] = [{"name": ps.name} for ps in payment_systems]

        currencies = Currency.objects.filter(paymentsystem__in=payment_systems).distinct()
        data["currencies"] = [{"name": currency.symbol} for currency in currencies]

    if hasattr(user, 'trader'):
        payment_systems = PaymentSystem.objects.filter(currency=user.trader.currency).distinct()
        data["traffic_type"] = [{"name": traffic.name} for traffic in traffic_types]
        data["payment_system"] = [{"name": ps.name} for ps in payment_systems]

        if user.trader.is_boss:
            traders = Trader.objects.filter(team=user.trader.team).distinct()
            data["traders"] = [{"name": trader.user.username} for trader in traders]

    if hasattr(user, 'teamlead'):
        payment_systems = PaymentSystem.objects.filter().distinct()
        data["traffic_type"] = [{"name": traffic.name} for traffic in traffic_types]
        data["payment_system"] = [{"name": ps.name} for ps in payment_systems]
        teams = TraderTeam.objects.filter(teamlead=user.teamlead)

        traders = Trader.objects.filter(team__in=teams).distinct()
        data["traders"] = [{"name": trader.user.username} for trader in traders]

    if hasattr(user, 'supportmember'):
        teams = user.supportmember.controlled_teams.all()
        data["teams"] = [{"name": team.name} for team in teams]
        data["traffic_type"] = [{"name": traffic.name} for traffic in traffic_types]
        traders = Trader.objects.filter(team__in=teams)
        data["traders"] = [{"name": trader.user.username} for trader in traders]

        currencies = Currency.objects.filter(trader__in=traders).distinct()
        data["currencies"] = [{"name": currency.symbol} for currency in currencies]

        payment_systems = PaymentSystem.objects.filter(currency__in=currencies).distinct()
        data["payment_system"] = [{"name": ps.name} for ps in payment_systems]

        if user.supportmember.is_head:
            merchants = Merchant.objects.all()
            data["merchants"] = [{"name": merch.user.username} for merch in merchants]

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_stats_orders(request, *args, **kwargs):
    daily = False
    if request.GET.get('time') == 'day':
        daily = True
    today = timezone.now().date()
    month_ago = today - timedelta(days=30)

    def get_stats(start_date):
        in_orders = InOrder.objects.filter(creation_date__gte=start_date)
        out_orders = OutOrder.objects.filter(creation_date__gte=start_date)

        successful_in_orders = in_orders.filter(status__name="Completed")
        successful_out_orders = out_orders.filter(status__name="Completed")

        in_order_sum = successful_in_orders.aggregate(
            amount_sum=Sum('amount'),
            usd_amount_sum=Sum('usd_amount'),
            profit_sum=Sum(F('merchant_fee') - F('trader_fee')),
            count=Count('id')
        )

        out_order_sum = successful_out_orders.aggregate(
            amount_sum=Sum('amount'),
            usd_amount_sum=Sum('usd_amount'),
            profit_sum=Sum(F('merchant_fee') - F('trader_fee')),
            count=Count('id')
        )

        in_orders_all_sum = in_orders.aggregate(
            amount_sum=Sum('amount'),
            usd_amount_sum=Sum('usd_amount'),
        )

        out_orders_all_sum = out_orders.aggregate(
            amount_sum=Sum('amount'),
            usd_amount_sum=Sum('usd_amount'),
        )

        total_amount = (out_orders_all_sum['amount_sum'] or 0) + (in_orders_all_sum['amount_sum'] or 0)
        total_amount_usd = (out_orders_all_sum['usd_amount_sum'] or 0) + (in_orders_all_sum['usd_amount_sum'] or 0)

        in_orders_num = in_orders.count()
        out_orders_num = out_orders.count()
        fiat_inorder = in_order_sum['amount_sum'] or 0
        usd_inorder = in_order_sum['usd_amount_sum'] or 0
        fiat_outorder = out_order_sum['amount_sum'] or 0
        usd_outorder = out_order_sum['usd_amount_sum'] or 0

        inorder_profit = in_order_sum['profit_sum'] or 0
        outorder_profit = out_order_sum['profit_sum'] or 0

        inorder_success = (in_order_sum['count'] or 0)
        outorder_success = (out_order_sum['count'] or 0)

        total_profit = inorder_profit + outorder_profit if inorder_profit + outorder_profit > 0 else 1
        return [
            {"name": 'Кол-во заявок созданных (ввод)', "value": in_orders_num},
            {"name": 'Кол-во заявок созданных (вывод)', "value": out_orders_num},
            {"name": 'Кол-во заявок оплаченных (ввод)', "value": inorder_success},
            {"name": 'Кол-во заявок оплаченных (вывод)', "value": outorder_success},
            {"name": 'Сумма оплаченных заявок (ввод)', "value": f"{usd_inorder}$ ({fiat_inorder}₽)"},
            {"name": 'Сумма оплаченных заявок (вывод)', "value": f"{usd_outorder}$ ({fiat_outorder}₽)"},
            {"name": 'Общий оборот', "value": f"{total_amount_usd}$ ({total_amount}₽)"},
            {"name": 'Маржа (ввод)', "value": f"{inorder_profit}$"},
            {"name": 'Маржа (вывод)', "value": f"{outorder_profit}$"},
            {"name": 'Маржа (всего)', "value": f"{inorder_profit + outorder_profit}$"},
            {"name": 'Маржинальность', "value": f"{round(100 * (inorder_profit + outorder_profit) / total_amount_usd, 2)}%" if total_amount_usd > 0 else 0},
            {"name": 'Конверсия прием', "value": f"{round(100 * inorder_success / in_orders_num, 2) if in_orders_num > 0 else 0}%"},
            {"name": 'Конверсия выплаты', "value": f"{round(100 * outorder_success / out_orders_num, 2) if out_orders_num > 0 else 0}%"},
        ]

    if daily:
        return Response(status=status.HTTP_200_OK, data=get_stats(today))

    return Response(status=status.HTTP_200_OK, data=get_stats(month_ago))


@api_view(['GET'])
@permission_classes([HeadSupportPermission | DebugPermission])
def get_solutions(request, *args, **kwargs):
    user = request.user

    if not hasattr(user, 'supportmember'):
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})

    if not user.supportmember.is_head:
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not head of support!'})
    data = []
    teams = TraderTeam.objects.all()
    for team in teams:
        fee_objs = TraderTeamRates.objects.filter(team=team)
        fees = TraderTeamRatesSerializer(fee_objs, many=True)
        merchant_data = {'merchant_id': team.id, 'username': team.name, 'fees': fees.data}
        data.append(merchant_data)

    return Response(status=status.HTTP_200_OK, data=data)