from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from basics.serializers import TraderShortSupportSerializer, TraderToTransferSerializer, \
    TraderFromTransferSerializer, PaymentSystemSerializer, PaymentSystemExchangeRateSerializer, \
    CurrencySerializer, TrafficTypeSerializer, TraderTeamRatesSerializer
from rest_framework import status
from rest_framework.response import Response
from basics.models import Trader, Currency, TraderTeam, Balance, TrafficType, PaymentSystem, TraderTeamRates
from basics.permissions import TraderPermission, DebugPermission, SupportPermission, HeadSupportPermission
from basics.serializers import TraderShortSerializer
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from basics.models import PaymentDetails
from merchant.models import Merchant
from titanpay.settings import SBER_NAME, TBANK_NAME
from trade.models import Address
from basics.utils import get_balances, get_range
from django.db.models import Min, Max, Sum
from decimal import Decimal
from django.db import transaction


@api_view(['POST'])
@permission_classes([IsAdminUser])
def autoclose_off(request, *args, **kwargs):
    ps = PaymentSystem.objects.all()
    for p in ps:
        p.auto_close_amount = Decimal(-1)
        p.save()

    return Response(status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def autoclose_on(request, *args, **kwargs):
    ps = PaymentSystem.objects.all()
    for p in ps:
        p.auto_close_amount = Decimal(3000)
        p.save()

    return Response(status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_trading_team_support(request, *args, **kwargs):
    user = request.user
    if not hasattr(user, 'supportmember'):
        return Response(status=status.HTTP_403_FORBIDDEN, data={'details': 'You are not a support member'})

    teams = user.supportmember.controlled_teams.all()
    data = []
    for team in teams:
        fees = TraderTeamRates.objects.filter(team=team)
        team_data = {'team_id': team.id, 'team_name': team.name, 'senior_trader': [], 'traders': [], 'rate_in': team.rate_in, 'rate_out': team.rate_out, 'fees': TraderTeamRatesSerializer(fees, many=True).data}
        traders = Trader.objects.filter(team=team)

        for trader in traders:
            serializer = TraderShortSupportSerializer(trader)
            serializer_data = serializer.data
            if trader.is_boss:
                team_data['senior_trader'].append(serializer_data)
            else:
                team_data['traders'].append(serializer_data)
        data.append(team_data)
    return Response(status=status.HTTP_200_OK, data={'data': data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_trading_team_trader(request, *args, **kwargs):
    user = request.user
    if not hasattr(user, 'trader'):
        return Response(status=status.HTTP_403_FORBIDDEN, data={'details': 'You are not a trader'})
    team_data = {'team_id': user.trader.team.id, 'senior_trader': [], 'traders': [], 'rate_in': user.trader.team.rate_in, 'rate_out': user.trader.team.rate_out}
    traders = Trader.objects.filter(team=user.trader.team)
    for trader in traders:
        serializer = TraderShortSerializer(trader)
        serializer_data = serializer.data
        if trader.is_boss:
            team_data['senior_trader'].append(serializer_data)
        else:
            team_data['traders'].append(serializer_data)

    return Response(status=status.HTTP_200_OK, data={'data': [team_data]})


@api_view(['GET'])
@permission_classes([TraderPermission | DebugPermission])
def get_transfer_targets(request, *args, **kwargs):
    user = request.user
    if not user.is_authenticated:
        return Response(status=status.HTTP_403_FORBIDDEN, data={'details': 'You are not authenticated!'})

    if not hasattr(user, 'trader'):
        return Response(status=status.HTTP_403_FORBIDDEN, data={'details': 'You are not a trader'})

    if not user.trader.is_boss:
        boss = user.trader.boss
        boss_serializer = TraderToTransferSerializer(boss)
        boss_serializer_data = boss_serializer.data

        me_serializer = TraderFromTransferSerializer(user.trader)
        me_serializer_data = me_serializer.data
        return Response(status=status.HTTP_200_OK, data={"to": [boss_serializer_data], "from": [me_serializer_data]})

    traders = Trader.objects.filter(team=user.trader.team)

    serializer_from = TraderFromTransferSerializer(traders, many=True)
    serializer_from_data = serializer_from.data

    serializer_to = TraderToTransferSerializer(traders, many=True)
    serializer_to_data = serializer_to.data

    return Response(status=status.HTTP_200_OK, data={"to": serializer_to_data, "from": serializer_from_data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def update_balances(request, *args, **kwargs):
    deposits = get_balances()
    for deposit in deposits:
        if deposit["amount"] == 0:
            continue
        address = Address.objects.get(address_public=deposit["address"])
        address.update_balance(Decimal(deposit["amount"]))

    return Response(status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([SupportPermission | DebugPermission])
def get_balances_stats(request, *args, **kwargs):
    user = request.user
    if not user.is_authenticated:
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not a trader'})

    if not hasattr(user, 'supportmember'):
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})
    data = {"data": []}
    total, total_frozen, total_earned = 0, 0, 0
    teams = user.supportmember.controlled_teams.all()

    currencies = Currency.objects.filter(trader__team__in=teams).distinct()
    for currency in currencies:
        sub_currency_data = {"currency": currency.symbol, "data": []}

        sub_teams = TraderTeam.objects.filter(trader__currency=currency).distinct()
        currency_total, currency_total_frozen = 0, 0

        for team in sub_teams:
            team_data = {"team_name": team.name, "data": []}
            traders = Trader.objects.filter(team=team).distinct()
            team_data["data"] = [{"username": trader.user.username,  "available_balance_amount": trader.balance_usdt.amount, "frozen_balance_amount": trader.frozen_balance_usdt.amount} for trader in traders]
            team_data["total_amount"] = sum([_trader["available_balance_amount"] for _trader in team_data["data"]])
            team_data["total_frozen"] = sum([_trader["frozen_balance_amount"] for _trader in team_data["data"]])
            team_data["insurance_deposit"] = team.insurance_deposit
            currency_total += team_data["total_amount"]
            currency_total_frozen += team_data["total_frozen"]
            sub_currency_data["data"].append(team_data)

        sub_currency_data["total_amount"] = currency_total
        sub_currency_data["total_frozen"] = currency_total_frozen

        total += currency_total
        total_frozen += currency_total_frozen

        data["data"].append(sub_currency_data)

    data["total_amount"] = total
    data["total_frozen"] = total_frozen

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([SupportPermission | DebugPermission])
def get_balance_filter_support(request, *args, **kwargs):
    user = request.user
    if not user.is_authenticated:
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not authenticated'})

    if not hasattr(user, 'supportmember'):
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})

    teams = user.supportmember.controlled_teams.all()
    traders = Trader.objects.filter(team__in=teams)
    data = {"teams": [{"name": team.name} for team in teams], "traders": [{"name": trader.user.username} for trader in traders],
            "system": [{"name": "Blockchain", "value": 3}, {"name": "Aggregator Balance", "value": 2}]}

    if user.supportmember.is_head:
        merchants = Merchant.objects.all()
        data['merchants'] = [{"name": merchant.user.username} for merchant in merchants]

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([TraderPermission | DebugPermission])
def get_balance_filter_trader(request, *args, **kwargs):
    user = request.user
    if not user.is_authenticated:
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not authenticated'})

    if not hasattr(user, 'trader'):
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not a trader!'})

    if not user.trader.is_boss:
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not a boss trader!'})

    traders = Trader.objects.filter(team=user.trader.team)

    data = {"traders": [{"name": trader.user.username} for trader in traders]}

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([SupportPermission | DebugPermission])
def get_user_filter_support(request, *args, **kwargs):
    user = request.user
    if not user.is_authenticated:
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not authenticated'})

    if not hasattr(user, 'supportmember'):
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})

    teams = user.supportmember.controlled_teams.all()
    traders = Trader.objects.filter(team__in=teams, is_boss=True)
    users = [{"name": trader.user.username} for trader in traders]

    if user.supportmember.is_head:
        merchants = Merchant.objects.all()
        users += [{"name": merch.user.username} for merch in merchants]

    return Response(status=status.HTTP_200_OK, data={"users": users})


@api_view(['GET'])
@permission_classes([TraderPermission | DebugPermission])
def get_pdgroup_creation_data(request, *args, **kwargs):
    currencies = Currency.objects.all()
    payment_systems = PaymentSystem.objects.filter(sbp_compatible=True)
    traffic_types = TrafficType.objects.all()

    data = dict()
    data["payment_systems"] = PaymentSystemSerializer(payment_systems, many=True).data
    data["currencies"] = CurrencySerializer(currencies, many=True).data
    data["traffic_types"] = TrafficTypeSerializer(traffic_types, many=True).data

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([TraderPermission | DebugPermission])
def get_pd_creation_data(request, *args, **kwargs):
    ps1 = PaymentSystem.objects.get(name=SBER_NAME)
    ps2 = PaymentSystem.objects.get(name=TBANK_NAME)

    data = {str(ps1.id): {"phone": {"type": "text", "unique": True, "cash": False}, "card_number": {"type": "number", "unique": False, "cash": False}, "deposit_number": {"type": "number", "unique": False, "cash": True}, "sberpay_enabled": {"type": "bool", "unique": True, "cash": False}, "sbp_enabled": {"type": "bool", "unique": True, "cash": False}}}
    data[str(ps2.id)] = {"phone": {"type": "text", "unique": True}, "card_number": {"type": "number", "unique": False}, "deposit_number": {"type": "number", "unique": False}, "sberpay_enabled": {"type": "bool", "unique": True}, "sbp_enabled": {"type": "bool", "unique": True}}
    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_filters_payment_details(request, *args, **kwargs):
    user = request.user
    data = {}
    traffic_types = TrafficType.objects.all()
    data["traffic_type"] = [{"name": traffic.name} for traffic in traffic_types]

    if hasattr(user, 'trader'):
        payment_systems = PaymentSystem.objects.filter(currency=user.trader.currency).distinct()
        data["status"] = [{"name": "Inactive", "value": 0}, {"name": "Active", "value": 1}, {"name": "Blocked by support", "value": 3}, {"name": "Arb Blocked", "value": 4}, {"name": "Auto Blocked", "value": 5}, {"name": "Blocked", "value": 6}, {"name": "Setup", "value": 7}]
        data["payment_system"] = [{"name": ps.name} for ps in payment_systems]

        if user.trader.is_boss:
            traders = Trader.objects.filter(team=user.trader.team).distinct()
            data["traders"] = [{"name": trader.user.username} for trader in traders]

    if hasattr(user, 'supportmember'):
        support_member = user.supportmember
        teams = support_member.controlled_teams.all()

        data["status"] = [{"name": "Inactive", "value": 0}, {"name": "Active", "value": 1}, {"name": "Archived", "value": 2}, {"name": "Blocked by support", "value": 3}, {"name": "Arb Blocked", "value": 4}, {"name": "Auto Blocked", "value": 5}, {"name": "Blocked", "value": 6}, {"name": "Setup", "value": 7}]
        teams = user.supportmember.controlled_teams.all()
        data["teams"] = [{"name": team.name} for team in teams]
        data["traffic_type"] = [{"name": traffic.name} for traffic in traffic_types]
        traders = Trader.objects.filter(team__in=teams)
        data["traders"] = [{"name": trader.user.username} for trader in traders]

        currencies = Currency.objects.filter(trader__in=traders).distinct()
        data["currencies"] = [{"name": currency.symbol} for currency in currencies]

        payment_systems = PaymentSystem.objects.filter(currency__in=currencies).distinct()
        data["payment_system"] = [{"name": ps.name} for ps in payment_systems]

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([HeadSupportPermission])
def get_exchange_rates(request, *args, **kwargs):
    payment_systems = PaymentSystem.objects.select_related('currency').order_by('name')
    data = PaymentSystemExchangeRateSerializer(payment_systems, many=True).data
    return Response(status=status.HTTP_200_OK, data=data)