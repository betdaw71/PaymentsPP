import datetime

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.decorators import action
from basics.models import Language, Currency, PaymentSystem, Trader, Balance, PaymentDetails, \
    TraderTeam, TrafficType, PaymentDetailsGroup, TeamLead, TraderTeamRates
from basics.paginators import StandardResultsSetPagination
from titanpay.settings import SBER_NAME, C2C_NAME, PROTOCOL_C2C_NAME, C2CTRY_NAME
from usermanagement.models import SupportMember
from merchant.models import Merchant
from trade.models import Transaction, TransactionType
from basics.serializers import LanguageSerializer, CurrencySerializer, PaymentSystemSerializer, TraderSerializer, \
    TraderBalanceSerializer, TransferSerializer, TraderCreateSerializer, SupportMemberSerializer, \
    SupportMemberCreateSerializer, TraderTeamSerializer, BalanceSerializer, TrafficTypeSerializer, \
    PaymentDetailsGroupCreateSerializer, PaymentDetailsGroupFullSerializer, PaymentDetailsGroupShortSerializer, \
    PaymentDetailsSberActionSerializer, PaymentDetailsGroupStatusSerializer, PaymentDetailsStatusSerializer, \
    RatesSerializer, PaymentDetailsSberAddSerializer, MinMaxAmountOutSerializer, TeamLeadSerializer, \
    DepositModeSerializer
from rest_framework import viewsets, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from basics.permissions import ReadOnly, SupportPermission, TraderPermission, MerchantPermission, HeadSupportPermission, \
    DebugPermission, TeamLeadPermission
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from decimal import Decimal
from django.db import transaction


class LanguageViewSet(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    permission_classes = [ReadOnly | IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get']


class CurrencyViewSet(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    permission_classes = [ReadOnly | IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get']


class PaymentSystemViewSet(viewsets.ModelViewSet):
    lookup_field = 'id'
    serializer_class = PaymentSystemSerializer
    permission_classes = [ReadOnly | IsAdminUser | IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['id', 'name', 'currency']
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get']

    def get_queryset(self):
        if hasattr(self.request.user, 'trader'):
            return PaymentSystem.objects.filter(currency=self.request.user.trader.currency)

        return PaymentSystem.objects.all()

class TrafficTypeViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = TrafficType.objects.all()
    serializer_class = TrafficTypeSerializer
    permission_classes = [HeadSupportPermission | IsAdminUser | DebugPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get']


class TeamLeadViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = TeamLead.objects.all()
    serializer_class = TeamLeadSerializer
    permission_classes = [HeadSupportPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get']


class TraderTeamViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = TraderTeam.objects.all()
    serializer_class = TraderTeamSerializer
    permission_classes = [HeadSupportPermission | IsAdminUser | DebugPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get', 'post']

    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='set_rates')
    @transaction.atomic
    def set_rates(self, request, id=None):
        team = TraderTeam.objects.get(id=id)
        support = self.request.user.supportmember

        if team not in support.controlled_teams.all():
            return Response(status=status.HTTP_403_FORBIDDEN, data={'details': 'Not your team!'})

        serializer = RatesSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        rate_in, rate_out = serializer.validated_data['rate_in'], serializer.validated_data['rate_out']

        team.set_rates(rate_in, rate_out)

        return Response(status=status.HTTP_200_OK)


class TraderViewSet(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = Trader.objects.all()
    serializer_class = TraderSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    http_method_names = ['get', 'post', 'patch']
    ordering = ['id']
    PROTECTED_FIELDS = ('team', 'boss', 'is_boss', 'user', 'balance_usdt', 'frozen_balance_usdt', 'blocked', 'currency')

    def partial_update(self, request, *args, **kwargs):
        if not hasattr(request.user, 'trader'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not a trader!'})

        instance = request.user.trader

        for field in request.data.keys():
            if field in self.PROTECTED_FIELDS:
                return Response({field: f"{field} cannot be changed"},
                                status=status.HTTP_400_BAD_REQUEST)
            if getattr(instance, field) and request.data.get(field) != getattr(instance, field):
                return Response({field: f"{field} can only be changed if it's empty."},
                                status=status.HTTP_400_BAD_REQUEST)

        return super(TraderViewSet, self).update(request, *args, **kwargs)

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [HeadSupportPermission | DebugPermission | TraderPermission]
        elif self.action == 'update':
            permission_classes = [TraderPermission | DebugPermission]
        else:
            permission_classes = [IsAuthenticated]

        return [permission() for permission in permission_classes]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})
        support_member: SupportMember = request.user.supportmember

        if not support_member.is_head:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not head of support!'})
        serializer = TraderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='block')
    @transaction.atomic
    def block(self, request, id=None):
        support_member: SupportMember = request.user.supportmember
        trader = Trader.objects.get(id=id)
        if trader.team not in support_member.controlled_teams.all():
            return Response(status=status.HTTP_403_FORBIDDEN,
                            data={'error': 'This trader is not under your control!'})
        trader.blocked = True
        trader.save()
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='unblock')
    @transaction.atomic
    def unblock(self, request, id=None):
        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})
        support_member: SupportMember = request.user.supportmember
        trader = Trader.objects.get(id=id)
        if trader.team not in support_member.controlled_teams.all():
            return Response(status=status.HTTP_403_FORBIDDEN,
                            data={'error': 'This trader is not under your control!'})
        trader.blocked = False
        trader.save()
        return Response(status=status.HTTP_200_OK)


class BalanceViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = Balance.objects.all()
    serializer_class = BalanceSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get', 'post']

    @action(detail=False, methods=['GET'], permission_classes=[SupportPermission | DebugPermission], url_path="support-merchant")
    def support_merchant(self, request):
        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})
        support_member: SupportMember = request.user.supportmember
        data_merchants = []

        merchants = Merchant.objects.all()
        for merchant in merchants:
            data_merchants.append({
                "id": merchant.id,
                "username": merchant.user.username,
                "available_balance_amount": merchant.balance.amount if merchant.balance else 0.0,
                "frozen_balance_amount": merchant.frozen_balance.amount if merchant.frozen_balance else 0.0,
            })

        return Response(status=status.HTTP_200_OK, data=data_merchants)

    @action(detail=False, methods=['GET'], permission_classes=[TraderPermission | DebugPermission])
    def trader(self, request):
        if not hasattr(request.user, 'trader'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not a trader!'})
        trader: Trader = request.user.trader

        my_balance = {
            "id": trader.id,
            "username": trader.user.username,
            "available_balance_amount": trader.balance_usdt.amount if trader.balance_usdt else 0.0,
            "available_balance_id": trader.balance_usdt.id,
            "frozen_balance_amount": trader.frozen_balance_usdt.amount if trader.frozen_balance_usdt else 0.0,
            "frozen_balance_id": trader.frozen_balance_usdt.id,
            "deposit_address": trader.balance_usdt.address.get().address_public if trader.is_boss else trader.boss.balance_usdt.address.get().address_public,
            "insurance_deposit": trader.team.insurance_deposit
        }

        serializer = TraderBalanceSerializer(my_balance)
        serialized_data = serializer.data

        balances = {'my_balance': serialized_data}

        subordinate_traders = Trader.objects.filter(boss=trader)
        subordinate_traders.select_related('balance_usdt', 'frozen_balance_usdt').all()
        data = []

        for sub_trader in subordinate_traders:
            data.append({
                "id": sub_trader.id,
                "username": sub_trader.user.username,
                "available_balance_amount": sub_trader.balance_usdt.amount if sub_trader.balance_usdt else 0.0,
                "available_balance_id": sub_trader.balance_usdt.id,
                "frozen_balance_amount": sub_trader.frozen_balance_usdt.amount if sub_trader.frozen_balance_usdt else 0.0,
                "frozen_balance_id": sub_trader.frozen_balance_usdt.id,
            })

        serializer = TraderBalanceSerializer(data, many=True)
        serialized_data = serializer.data
        balances["sub_balances"] = serialized_data

        return Response(status=status.HTTP_200_OK, data=balances)

    @action(detail=False, methods=['GET'], permission_classes=[MerchantPermission | DebugPermission])
    def merchant(self, request):

        if hasattr(request.user, 'merchant'):
            merchant: Merchant = request.user.merchant
            data = {
                "amount": merchant.balance.amount if merchant.balance else 0.0,
                "frozen_amount": merchant.frozen_balance.amount if merchant.frozen_balance else 0.0,
                "deposit_address": merchant.balance.address.get().address_public
            }
            return Response(status=status.HTTP_200_OK, data=data)
        elif hasattr(request.user, 'submerchant'):
            merchant: Merchant = request.user.submerchant.merchant
            data = {
                "amount": merchant.balance.amount if merchant.balance else 0.0,
                "frozen_amount": merchant.frozen_balance.amount if merchant.frozen_balance else 0.0,
                "deposit_address": merchant.balance.address.get().address_public
            }
            return Response(status=status.HTTP_200_OK, data=data)
        else:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not a merchant!'})

    @action(detail=False, methods=['GET'], permission_classes=[TeamLeadPermission | DebugPermission])
    def teamlead(self, request):

        teamlead: TeamLead = request.user.teamlead
        data = {
            "amount": teamlead.balance.amount if teamlead.balance else 0.0,
        }
        return Response(status=status.HTTP_200_OK, data=data)

    @action(detail=False, methods=['POST'], permission_classes=[TraderPermission | DebugPermission])
    @transaction.atomic
    def transfer(self, request):
        if not hasattr(request.user, 'trader'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not a trader!'})

        trader: Trader = request.user.trader

        serializer = TransferSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)

        data = serializer.validated_data
        from_balance_id = data["from_balance"]
        to_balance_id = data["to_balance"]
        amount = data["amount"]

        transaction_type = TransactionType.objects.get(name="Transfer")

        if from_balance_id == to_balance_id:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'From and To are the same'})

        if not Balance.objects.filter(id=from_balance_id).exists():
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'from_balance does not exist'})

        if not Balance.objects.filter(id=to_balance_id).exists():
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'to_balance does not exist'})

        from_balance = Balance.objects.get(id=from_balance_id)
        to_balance = Balance.objects.get(id=to_balance_id)

        if from_balance.type != 0 or to_balance.type != 0:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Wrong balance types!'})

        if from_balance.amount < amount:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Not enough funds!'})

        if 0 >= amount:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Amount should be more than zero!'})

        from_trader = from_balance.available.get()
        to_trader = to_balance.available.get()

        if not from_trader.team == to_trader.team == trader.team:
            return Response(status=status.HTTP_403_FORBIDDEN,
                            data={'error': 'Different teams, re-check the balances!'})

        if not trader.is_boss and from_trader != trader and to_trader != trader.boss:
            return Response(status=status.HTTP_403_FORBIDDEN,
                            data={'error': 'You can transfer only from your own balance to your boss'})

        try:
            amount = Decimal.from_float(amount)
            Transaction.create(_from=from_balance, _to=to_balance, value=amount, _transaction_type=transaction_type)
        except ValidationError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": e.message})

        return Response(status=status.HTTP_201_CREATED)


class SupportMemberViewSet(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = SupportMember.objects.all()
    serializer_class = SupportMemberSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get', 'post', 'patch']

    def get_permissions(self):
        if self.action == 'partial_update':
            permission_classes = [SupportPermission | HeadSupportPermission]
        else:
            permission_classes = [HeadSupportPermission | DebugPermission | SupportPermission]
        return [permission() for permission in permission_classes]

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        obj = self.get_object()
        has_access = False
        if obj.user == request.user:
            has_access = True

        if hasattr(request.user, 'supportmember'):
            if request.user.supportmember.is_head:
                has_access = True

        if not has_access:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are from support!'})

        return super(SupportMemberViewSet, self).update(request, *args, **kwargs)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = SupportMemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class PaymentDetailsGroupFilter(django_filters.FilterSet):
    class Meta:
        model = PaymentDetailsGroup
        fields = {
            'id': ['exact'],
            'status': ['in'],
            'owner': ['exact'],
            'trader__user__username': ['in'],
            'trader__team__name': ['in'],
            'currency__symbol': ['in'],
            'payment_system__name': ['in'],
        }


class PaymentDetailsGroupViewSet(viewsets.ModelViewSet):
    lookup_field = 'id'
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PaymentDetailsGroupFilter
    filterset_fields = ('merchant')
    pagination_class = StandardResultsSetPagination
    http_method_names = ['get', 'post']

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'supportmember'):

            support = user.supportmember
            if self.action == 'list':
                return PaymentDetailsGroup.objects.filter(trader__team__in=support.controlled_teams.all()).select_related('currency', 'trader', 'payment_system')
            elif self.action == 'retrieve':
                return PaymentDetailsGroup.objects.filter(trader__team__in=support.controlled_teams.all()).select_related('currency', 'trader', 'payment_system')
            else:
                return PaymentDetailsGroup.objects.none()
        elif hasattr(user, 'merchant'):
            return PaymentDetailsGroup.objects.none()
        elif hasattr(user, 'trader'):
            trader = user.trader

            if trader.is_boss:
                if self.action == 'list':
                    return PaymentDetailsGroup.objects.filter(trader__team=trader.team, status__in=[0, 1, 3, 4, 5, 6, 7]).select_related(
                        'currency', 'trader', 'payment_system')
                elif self.action == 'retrieve':
                    return PaymentDetailsGroup.objects.filter(trader__team=trader.team).select_related(
                        'currency', 'trader', 'payment_system')
                else:
                    return PaymentDetailsGroup.objects.none()
            else:
                if self.action == 'list':
                    return PaymentDetailsGroup.objects.filter(trader=trader, status__in=[0, 1, 3, 4, 5, 6, 7]).select_related(
                        'currency', 'trader', 'payment_system')
                elif self.action == 'retrieve':
                    return PaymentDetailsGroup.objects.filter(trader=trader).select_related(
                        'currency', 'trader', 'payment_system')
                else:
                    return PaymentDetailsGroup.objects.none()

        else:
            return PaymentDetailsGroup.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentDetailsGroupCreateSerializer
        elif self.action == 'retrieve':
            return PaymentDetailsGroupFullSerializer
        elif self.action == 'list':
            return PaymentDetailsGroupShortSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(trader=self.request.user.trader)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[TraderPermission], url_path='add-details')
    def add_details(self, request, id=None):

        group = PaymentDetailsGroup.objects.get(id=id)

        if group.trader != self.request.user.trader:
            return Response(status=status.HTTP_403_FORBIDDEN)

        ps_name = group.payment_system.name

        data = request.data
        data['group'] = str(group.id)

        if ps_name in (SBER_NAME, C2C_NAME, PROTOCOL_C2C_NAME):
            serializer = PaymentDetailsSberAddSerializer(data=request.data)
        elif ps_name == C2CTRY_NAME:
            serializer = PaymentDetailsSberAddSerializer(data=request.data)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'This payment system is not supported'})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer_data = serializer.validated_data

        details_group = serializer_data['group']

        if details_group != group:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Wrong payment details group'})

        serializer.save()

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[TraderPermission], url_path='change-details-status')
    def change_details_status(self, request, id=None):
        serializer = PaymentDetailsStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)

        serializer_data = serializer.validated_data

        group = PaymentDetailsGroup.objects.get(id=id)

        trader: Trader = request.user.trader

        if not (group.trader == trader or group.trader.boss == trader):
            return Response(status=status.HTTP_403_FORBIDDEN)

        details = serializer_data['details']

        if details.group != group:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Wrong group!'})

        details.status = serializer_data['status']
        details.save()

        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], permission_classes=[TraderPermission | DebugPermission | SupportPermission], url_path='in-out')
    @transaction.atomic
    def change_in_out_status(self, request, id=None):
        serializer = PaymentDetailsGroupStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)

        serializer_data = serializer.validated_data

        payment_detail = PaymentDetailsGroup.objects.get(id=id)

        if hasattr(request.user, 'trader'):
            trader: Trader = request.user.trader
            if not (payment_detail.trader == trader or payment_detail.trader.boss == trader):
                return Response(status=status.HTTP_403_FORBIDDEN)
        elif hasattr(request.user, 'supportmember'):
            if not request.user.supportmember:
                return Response(status=status.HTTP_403_FORBIDDEN)

        if serializer_data.get("status", None) == 1:
            payment_detail.in_active = False
            payment_detail.out_active = True
            payment_detail.save()
        elif serializer_data.get("status", None) == 0:
            payment_detail.in_active = True
            payment_detail.out_active = False
            payment_detail.save()
        elif serializer_data.get("status", None) == 2:
            payment_detail.in_active = True
            payment_detail.out_active = True
            payment_detail.save()

        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | TraderPermission | DebugPermission], url_path='change-status')
    @transaction.atomic
    def change_status(self, request, id=None):
        serializer = PaymentDetailsGroupStatusSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)

        serializer_data = serializer.validated_data

        group = PaymentDetailsGroup.objects.get(id=id)

        new_status = serializer_data.get("status", None)

        if hasattr(request.user, 'trader'):
            trader: Trader = request.user.trader
            if not (group.trader == trader or group.trader.boss == trader):
                return Response(status=status.HTTP_403_FORBIDDEN)

            if new_status not in [0, 1, 2]:
                return Response(status=status.HTTP_403_FORBIDDEN)

            group.status = new_status
            group.save()
            if new_status == 2:
                details = PaymentDetails.objects.filter(group=group)
                for detail in details:
                    detail.status = 0
                    detail.save()

        if hasattr(request.user, 'supportmember'):
            support_member: SupportMember = request.user.supportmember
            if group.trader.team not in support_member.controlled_teams.all():
                return Response(status=status.HTTP_403_FORBIDDEN)

            if new_status not in [0, 1, 2, 3]:
                return Response(status=status.HTTP_403_FORBIDDEN)

            group.status = new_status
            group.save()

            if new_status == 2:
                details = PaymentDetails.objects.filter(group=group)
                for detail in details:
                    detail.status = 0
                    detail.save()

        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | TraderPermission],  url_path='set-limits')
    @transaction.atomic
    def set_limits(self, request, id=None):
        serializer = MinMaxAmountOutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)

        serializer_data = serializer.validated_data

        group = PaymentDetailsGroup.objects.get(id=id)

        group.min_amount_out = serializer_data['min_amount_out']
        group.max_amount_out = serializer_data['max_amount_out']
        group.limit_per_period = serializer_data['volume_in']
        group.save()

        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], permission_classes=[TraderPermission], url_path='dep-mode')
    @transaction.atomic
    def dep_mode(self, request, id=None):
        serializer = DepositModeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)

        serializer_data = serializer.validated_data

        group = PaymentDetailsGroup.objects.get(id=id)

        group.deposit_number_on = serializer_data['on']
        group.save()

        return Response(status=status.HTTP_200_OK)


