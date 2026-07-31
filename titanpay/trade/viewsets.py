from datetime import timedelta
from decimal import Decimal

from django_filters.rest_framework import DjangoFilterBackend
import django_filters
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q
from rest_framework.decorators import action
from basics.models import Trader, Balance, PaymentDetails, TraderTeam, TraderTeamRates
from basics.serializers import TraderTeamSerializer, TraderTeamRatesSerializer
from payments.models import PayOut
from trade.utils2 import send_to_fastapi, orders_excel_http_response
from usermanagement.models import SupportMember
from trade.serializers import WithdrawalRequestSupportSerializer, WithdrawalRequestBasicSerializer, \
    WithdrawalRequestCreateSerializer, WithdrawalRequestApproveSerializer, WithdrawalRequestRejectSerializer, \
    InOrderSupportSerializer, InOrderMerchantSerializer, \
    TransactionIdSerializer, OutOrderMerchantSerializer, \
    OutOrderSupportSerializer, CommentSerializer, TransactionTraderSerializer, \
    TransactionMerchantSerializer, TransactionSupportSerializer, MoveSerializer, RecalculateSerializer, \
    InOrderTraderBossListSerializer, \
    InOrderTraderBossFullSerializer, InOrderTraderListSerializer, InOrderTraderFullSerializer, \
    OutOrderTraderBossListSerializer, OutOrderTraderBossFullSerializer, OutOrderTraderListSerializer, \
    OutOrderTraderFullSerializer, TransactionSubMerchantSerializer, TransactionTeamLeadSerializer, \
    InOrderTeamLeadSerializer, OutOrderTeamLeadSerializer, InOrderMerchantListSerializer, InOrderSupportListSerializer, \
    OutOrderMerchantListSerializer, OutOrderSupportListSerializer, OutOrderCheckSerializer, RecalculateTraderSerializer, \
    InOrderAgentMerchantSerializer, OutOrderAgentMerchantSerializer
from merchant.models import Merchant
from trade.models import WithdrawalRequest, Transaction, InOrder, OutOrder, Address, TransactionType
from rest_framework import viewsets, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from basics.permissions import SupportPermission, TraderPermission, DebugPermission, MerchantPermission, \
    HeadSupportPermission
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from basics.paginators import StandardResultsSetPagination
from django.db.models import Sum
from django.db import transaction
from django.utils import timezone


class WithdrawalRequestFilter(django_filters.FilterSet):
    class Meta:
        model = WithdrawalRequest
        fields = {
            'id': ['exact'],
            'status': ['in'],
            'amount': ['gte', 'lte'],
            'date': ['range'],
            'from_user__username': ['in'],
            'comment': ['exact'],
            'address_to': ['exact'],
        }


class WithdrawalRequestViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = WithdrawalRequestFilter
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['-date']
    pagination_class = StandardResultsSetPagination
    http_method_names = ['get', 'post']

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission])
    def approve(self, request, id=None):
        serializer = WithdrawalRequestApproveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)
        serializer_data = serializer.validated_data

        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})

        support_member: SupportMember = request.user.supportmember

        teams = support_member.controlled_teams.all()
        withdrawal_request = WithdrawalRequest.objects.get(id=id)

        if withdrawal_request.balance.available_merchant.exists() or withdrawal_request.balance.teamlead.exists():
            if not support_member.is_head:
                return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not head of support ot do that!'})

            try:
                withdrawal_request.approve(serializer_data["tx_id"])
            except ValidationError as e:
                return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)

            return Response(status=status.HTTP_200_OK)

        trader = withdrawal_request.balance.available.get()
        if trader.team not in teams:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You have no control over this team!'})

        try:
            withdrawal_request.approve(serializer_data["tx_id"])
        except ValidationError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission])
    def reject(self, request, id=None):
        serializer = WithdrawalRequestRejectSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)
        serializer_data = serializer.validated_data

        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})

        support_member: SupportMember = request.user.supportmember

        teams = support_member.controlled_teams.all()
        withdrawal_request = WithdrawalRequest.objects.get(id=id)

        if withdrawal_request.balance.available_merchant.exists() or withdrawal_request.balance.teamlead.exists():
            if not support_member.is_head:
                return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not head of support ot do that!'})

            try:
                withdrawal_request.reject(serializer_data["comment"])
            except ValidationError as e:
                return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)

            return Response(status=status.HTTP_200_OK)

        trader = withdrawal_request.balance.available.get()
        if trader.team not in teams:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You have no control over this team!'})
        try:
            withdrawal_request.reject(serializer_data["comment"])
        except ValidationError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)

        return Response(status=status.HTTP_200_OK)

    def get_serializer_class(self):
        if hasattr(self.request.user, 'trader') or hasattr(self.request.user, 'merchant') or hasattr(self.request.user, 'teamlead'):
            return WithdrawalRequestBasicSerializer
        if hasattr(self.request.user, 'supportmember'):
            return WithdrawalRequestSupportSerializer
        return WithdrawalRequestBasicSerializer

    def get_queryset(self):
        if hasattr(self.request.user, 'trader') or hasattr(self.request.user, 'merchant'):
            balance = self.request.user.trader.balance_usdt if hasattr(self.request.user, 'trader') else self.request.user.merchant.balance
            return WithdrawalRequest.objects.filter(balance=balance)

        if hasattr(self.request.user, 'teamlead'):
            return WithdrawalRequest.objects.filter(balance=self.request.user.teamlead.balance)

        if not hasattr(self.request.user, 'supportmember'):
            return WithdrawalRequest.objects.none()

        support_member: SupportMember = self.request.user.supportmember

        teams = support_member.controlled_teams.all()

        bosses = Trader.objects.filter(team__in=teams, is_boss=True)

        balances = Balance.objects.filter(available__in=bosses)

        if not support_member.is_head:
            return WithdrawalRequest.objects.filter(balance__in=balances)

        merchants = Merchant.objects.all()
        merchant_balances = Balance.objects.filter(available_merchant__in=merchants)
        query = WithdrawalRequest.objects.filter(Q(balance__in=merchant_balances) | Q(balance__in=balances))
        return query

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = WithdrawalRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer_data = serializer.validated_data

        if hasattr(request.user, 'merchant'):
            merchant = request.user.merchant
            if merchant.balance.amount < serializer_data["amount"]:
                return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Not enough funds!'})
            try:
                WithdrawalRequest.create(_from=merchant.balance, amount=serializer_data["amount"],
                                     address_to=serializer_data["address"], from_user=request.user)
            except ValidationError as e:
                return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)
            return Response(status=status.HTTP_201_CREATED)

        if hasattr(request.user, 'teamlead'):
            teamlead = request.user.teamlead
            if teamlead.balance.amount < serializer_data["amount"]:
                return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Not enough funds!'})
            try:
                WithdrawalRequest.create(_from=teamlead.balance, amount=serializer_data["amount"],
                                     address_to=serializer_data["address"], from_user=request.user)
            except ValidationError as e:
                return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)
            return Response(status=status.HTTP_201_CREATED)

        if not hasattr(request.user, 'trader'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You cannot withdraw!'})

        trader = request.user.trader

        if not trader.is_boss:
            return Response(status=status.HTTP_403_FORBIDDEN,
                            data={'error': 'You are not a senior trader to do that!'})

        if trader.balance_usdt.amount < serializer_data["amount"]:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Not enough funds!'})

        try:
            WithdrawalRequest.create(_from=trader.balance_usdt, amount=serializer_data["amount"],
                                 address_to=serializer_data["address"], from_user=request.user)
        except ValidationError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)

        return Response(status=status.HTTP_201_CREATED)


class TransactionFilter(django_filters.FilterSet):
    class Meta:
        model = Transaction
        fields = {
            'id': ['exact'],
            'transaction_type__name': ['in'],  # Transaction Type Name
            'value': ['gte', 'lte'],
            'creation_date': ['range'],
            'linked_in_order': ['exact'],
            'linked_out_order': ['exact'],
            'from_balance': ['exact'],
            'to_balance': ['exact'],
            'from_balance__available__user__username': ['in'],  # from: Trader username
            'from_balance__available_merchant__user__username': ['in'],  # from: Merchant username
            'from_balance__available__team__name': ['in'],  # from: Trader team name
            'to_balance__available__user__username': ['in'],  # to: Trader username
            'to_balance__available_merchant__user__username': ['in'],  # to: Merchant username
            'to_balance__available__team__name': ['in'],  # to: Trader team name
            'to_balance__type': ['in'],  # to: (2 or 3) for internal Balances
            'from_balance__type': ['in'],  # to: (2 or 3) for internal Balances
        }


class TransactionViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TransactionFilter
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['-creation_date']
    pagination_class = StandardResultsSetPagination
    http_method_names = ['get']

    def get_serializer_class(self):
        if hasattr(self.request.user, 'trader'):
            if self.request.user.trader.is_boss:
                return TransactionSupportSerializer
            return TransactionTraderSerializer
        if hasattr(self.request.user, 'merchant'):
            return TransactionMerchantSerializer
        if hasattr(self.request.user, 'submerchant'):
            return TransactionSubMerchantSerializer
        if hasattr(self.request.user, 'teamlead'):
            return TransactionTeamLeadSerializer
        if hasattr(self.request.user, 'supportmember'):
            return TransactionSupportSerializer
        return TransactionTraderSerializer

    def get_queryset(self):
        if hasattr(self.request.user, 'trader') or hasattr(self.request.user, 'merchant'):
            balance = self.request.user.trader.balance_usdt if hasattr(self.request.user, 'trader') else self.request.user.merchant.balance
            frozen_balance = self.request.user.trader.frozen_balance_usdt if hasattr(self.request.user, 'trader') else self.request.user.merchant.frozen_balance
            combined_queryset = Transaction.objects.filter(Q(from_balance=balance) | Q(to_balance=balance) | Q(from_balance=frozen_balance) | Q(to_balance=frozen_balance))
            return combined_queryset

        if hasattr(self.request.user, 'submerchant'):
            balance = self.request.user.submerchant.merchant.balance
            frozen_balance = self.request.user.submerchant.merchant.balance
            combined_queryset = Transaction.objects.filter(Q(from_balance=balance) | Q(to_balance=balance) | Q(from_balance=frozen_balance) | Q(to_balance=frozen_balance))
            return combined_queryset

        if hasattr(self.request.user, 'teamlead'):
            balance = self.request.user.teamlead.balance
            combined_queryset = Transaction.objects.filter(Q(from_balance=balance) | Q(to_balance=balance))
            return combined_queryset

        if not hasattr(self.request.user, 'supportmember'):
            return Transaction.objects.none()

        support_member: SupportMember = self.request.user.supportmember

        teams = support_member.controlled_teams.all()

        if support_member.is_head:
            merchants = Merchant.objects.all()
            balances = Balance.objects.filter(Q(available__team__in=teams) | Q(trader_frozen__team__in=teams) | Q(available_merchant__in=merchants) | Q(frozen_merchant__in=merchants))
        else:
            balances = Balance.objects.filter(Q(available__team__in=teams) | Q(trader_frozen__team__in=teams))

        queryset = Transaction.objects.filter(Q(from_balance__in=balances) | Q(to_balance__in=balances))
        return queryset


class InOrderFilter(django_filters.FilterSet):
    class Meta:
        model = InOrder
        fields = {
            'id': ['exact'],
            'creation_date': ['range'],
            'payment_details__group__trader__user__username': ['in'],
            'payment_details__group__trader__team__name': ['in'],
            'status__name': ['in'],
            'amount': ['lte', 'gte'],
            'usd_amount': ['lte', 'gte'],
            'solution__payment_system__currency__symbol': ['in'],
            'solution__payment_system__name': ['in'],
            'solution__merchant__user__username': ['in'],
            'solution__traffic__name': ['in'],
            'payment_details__id': ['exact'],
            'payment_details__group__owner': ['icontains'],
            'payment_details__group__id': ['exact'],
            'payment_details__card_number': ['exact'],
            'merchant_order_id': ['exact'],
            'pay_in__id': ['exact'],
            'pay_in__client__client_id': ['exact'],
        }


def _support_in_orders_queryset(support_member: SupportMember):
    """Заявки саппорта, включая Cannot process без payment_details (не прошли роутинг)."""
    if support_member.is_head:
        return InOrder.objects.all()

    merchants = support_member.controlled_merchants.all()
    teams = support_member.controlled_teams.all()
    if not merchants.exists() and not teams.exists():
        return InOrder.objects.none()

    cannot_process = Q(
        payment_details__isnull=True,
        status__name='Cannot process',
    )
    if merchants.exists():
        cannot_process &= Q(solution__merchant__in=merchants)

    if merchants.exists() and teams.exists():
        routed = Q(solution__merchant__in=merchants) & Q(
            payment_details__group__trader__team__in=teams
        )
        return InOrder.objects.filter(routed | cannot_process)

    if merchants.exists():
        return InOrder.objects.filter(solution__merchant__in=merchants)

    ps_ids = TraderTeamRates.objects.filter(team__in=teams).values_list(
        'payment_system_id', flat=True
    ).distinct()
    cannot_process_team = Q(
        payment_details__isnull=True,
        status__name='Cannot process',
        solution__payment_system_id__in=ps_ids,
    )
    return InOrder.objects.filter(
        Q(payment_details__group__trader__team__in=teams) | cannot_process_team
    )


class InOrderViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = InOrderFilter
    filterset_fields = ['creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'solution', 'payment_details']
    search_fields = ['creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'solution', 'payment_details']
    ordering_fields = ['creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'solution', 'payment_details']
    ordering = ['-creation_date']
    pagination_class = StandardResultsSetPagination
    http_method_names = ['get', 'post']

    def get_queryset(self):
        if hasattr(self.request.user, 'trader'):
            from payments.psp_payin import filter_inorders_for_trader_lk, is_psp_trader

            trader: Trader = self.request.user.trader
            if is_psp_trader(trader):
                return InOrder.objects.none()
            if self.request.user.trader.is_boss:
                orders = InOrder.objects.filter(payment_details__group__trader__team=trader.team)
            else:
                orders = InOrder.objects.filter(payment_details__group__trader=trader)
            return filter_inorders_for_trader_lk(orders)

        if hasattr(self.request.user, 'supportmember'):
            return _support_in_orders_queryset(self.request.user.supportmember)

        if hasattr(self.request.user, 'merchant'):
            merchant: Merchant = self.request.user.merchant
            orders = InOrder.objects.filter(solution__merchant=merchant)
            return orders

        if hasattr(self.request.user, 'submerchant'):
            merchant: Merchant = self.request.user.submerchant.merchant
            orders = InOrder.objects.filter(solution__merchant=merchant)
            return orders

        if hasattr(self.request.user, 'teamlead'):
            from payments.psp_payin import filter_inorders_for_trader_lk
            from trade.agent_commission import merchant_ids_for_agent
            from trade.teamlead_scope import teamlead_order_scope

            teamlead = self.request.user.teamlead
            if teamlead_order_scope(self.request) == 'merchant':
                merchant_ids = merchant_ids_for_agent(teamlead)
                return InOrder.objects.filter(solution__merchant_id__in=merchant_ids)

            teams = TraderTeam.objects.filter(teamlead=teamlead)
            orders = InOrder.objects.filter(payment_details__group__trader__team__in=teams)
            return filter_inorders_for_trader_lk(orders)

        return InOrder.objects.none()

    def get_serializer_class(self):
        if hasattr(self.request.user, 'trader'):
            if self.request.user.trader.is_boss:
                if self.action == 'list':
                    return InOrderTraderBossListSerializer
                else:
                    return InOrderTraderBossFullSerializer
            else:
                if self.action == 'list':
                    return InOrderTraderListSerializer
                else:
                    return InOrderTraderFullSerializer
        if hasattr(self.request.user, 'merchant') or hasattr(self.request.user, 'submerchant'):
            if self.action == 'list':
                return InOrderMerchantListSerializer
            else:
                return InOrderMerchantSerializer
        if hasattr(self.request.user, 'teamlead'):
            from trade.teamlead_scope import teamlead_order_scope

            if teamlead_order_scope(self.request) == 'merchant':
                return InOrderAgentMerchantSerializer
            return InOrderTeamLeadSerializer
        if hasattr(self.request.user, 'supportmember'):
            if self.action == 'list':
                return InOrderSupportListSerializer
            else:
                return InOrderSupportSerializer
        return InOrderTraderListSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        status_filter = (request.query_params.get('status__name__in') or '').strip()
        status_names = [s.strip() for s in status_filter.split(',') if s.strip()]
        # «Cannot process» скрывали всегда — из-за этого отклонённые заявки не попадали в «Отклонённые»
        if status_names and 'Cannot process' not in status_names:
            queryset = queryset.exclude(status__name="Cannot process")
        elif not status_names:
            pass  # вкладка «Все» — показываем в том числе Cannot process

        completed = queryset.filter(status__name="Completed")
        total_usd_amount = completed.aggregate(sum_usd_amount=Sum('usd_amount'))['sum_usd_amount'] or 0

        if hasattr(self.request.user, 'merchant'):
            total_commission = completed.aggregate(sum_usd_amount=Sum('merchant_fee'))['sum_usd_amount'] or 0
            hold = Decimal(0)
        elif hasattr(self.request.user, 'supportmember'):
            total_commission_merchant = completed.aggregate(sum_usd_amount=Sum('merchant_fee'))['sum_usd_amount'] or 0
            total_commission_trader = completed.aggregate(sum_usd_amount=Sum('trader_fee'))['sum_usd_amount'] or 0
            total_commission = total_commission_merchant - total_commission_trader
            hold = Decimal(0)
        elif hasattr(self.request.user, 'teamlead'):
            from trade.teamlead_scope import teamlead_order_scope

            if teamlead_order_scope(self.request) == 'merchant':
                total_commission = completed.aggregate(sum_usd_amount=Sum('agent_fee'))['sum_usd_amount'] or 0
                hold = Decimal(0)
            else:
                total_commission = completed.aggregate(sum_usd_amount=Sum('trader_fee'))['sum_usd_amount'] or 0
                holded_orders = queryset.filter(status__name__in=['New', 'Arbitrage', 'Money sent by user'])
                hold = holded_orders.aggregate(sum_usd_amount=Sum('usd_amount'))['sum_usd_amount'] or 0
        else:
            total_commission = completed.aggregate(sum_usd_amount=Sum('trader_fee'))['sum_usd_amount'] or 0
            holded_orders = queryset.filter(status__name__in=['New', 'Arbitrage', 'Money sent by user'])
            hold = holded_orders.aggregate(sum_usd_amount=Sum('usd_amount'))['sum_usd_amount'] or 0

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
        else:
            serializer = self.get_serializer(queryset, many=True)
            response = Response(serializer.data)

        response.data['total_usd_amount'] = total_usd_amount
        response.data['total_commission'] = total_commission
        response.data['hold'] = hold

        return response

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='money-sent')
    def money_sent(self, request, id=None):
        # TODO: permissions
        if not InOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
        order = InOrder.objects.select_for_update().get(id=id)

        order.change_to_money_sent_by_user()

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | TraderPermission | DebugPermission], url_path='cancel')
    def cancel(self, request, id=None):
        if not InOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})

        order = InOrder.objects.get(id=id)

        if hasattr(request.user, 'supportmember'):

            support_member = request.user.supportmember

            if order.payment_details.group.trader.team not in support_member.controlled_teams.all():
                return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'This order is not under your control!'})

            order.cancel_by_support()

            return Response(status=status.HTTP_200_OK)

        else:

            if request.user.trader.is_boss:
                if order.payment_details.group.trader.team != request.user.trader.team:
                    return Response(status=status.HTTP_403_FORBIDDEN,
                                    data={'error': 'This order is not under your control!'})
            else:
                if order.payment_details.group.trader != request.user.trader:
                    return Response(status=status.HTTP_403_FORBIDDEN,
                                    data={'error': 'This order is not under your control!'})
                
            serializer = CommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer_data = serializer.validated_data
            order.cancel_by_trader(rejection_reason=serializer_data.get("trader_comment", ""))
            return Response(status=status.HTTP_200_OK)

    # @transaction.atomic
    # @action(detail=True, methods=['POST'], permission_classes=[TraderPermission | DebugPermission])
    # def arbitrage(self, request, id=None):
    #     if not hasattr(request.user, 'trader'):
    #         return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not a trader!'})
    #
    #     trader: Trader = request.user.trader
    #
    #     if not InOrder.objects.filter(id=id).exists():
    #         return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
    #     order = InOrder.objects.get(id=id)
    #
    #     if order.payment_details.group.trader != trader:
    #         return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'It is not your order!'})
    #
    #     order.arbitrage()
    #
    #     return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='arbitrage-support')
    def arbitrage_support(self, request, id=None):
        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})
        support: SupportMember = request.user.supportmember
        if not InOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
        order = InOrder.objects.get(id=id)

        if order.payment_details.group.trader.team not in support.controlled_teams.all():
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'It is not your order!'})

        order.arbitrage_support()

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='complete-support')
    def complete_support(self, request, id=None):
        if not InOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'You are not from support'})
        order = InOrder.objects.select_for_update().get(id=id)
        if order.status.name == "Completed":
            return Response(status=status.HTTP_409_CONFLICT, data={'error': 'Order already completed'})
        support_member = request.user.supportmember
        if order.payment_details.group.trader.team not in support_member.controlled_teams.all():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'This order is not under your control!'})
        order.complete_after_recalc()
        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[TraderPermission | DebugPermission])
    def complete(self, request, id=None):
        if not hasattr(request.user, 'trader'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not a trader!'})
        trader: Trader = request.user.trader
        if not InOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
        order = InOrder.objects.select_for_update().get(id=id)
        if order.status.name == "Completed":
            return Response(status=status.HTTP_409_CONFLICT, data={'error': 'Order already completed'})
        if order.payment_details.group.trader != trader:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'It is not your order!'})
        if order.status.name == "Arbitrage":
            order.complete_after_arbitrage()
        elif order.status.name == "Expired":
            order.complete_after_expired()
        elif order.status.name == "Money sent by user" or order.status.name == "New":
            order.complete_after_new()
        else:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'Order cannot be completed!'})
        return Response(status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='move')
    def move(self, request, id=None):
        if not InOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support'})
        order = InOrder.objects.get(id=id)
        support_member = request.user.supportmember

        if order.solution.merchant not in support_member.controlled_merchants.all():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'This order is not under your control!'})

        serializer = MoveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)
        serializer_data = serializer.validated_data
        details = serializer_data['details']
        # if details == order.payment_details:
        #     return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Cannot move to the same details'})
        order.move(details)
        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | TraderPermission | DebugPermission], url_path='recalculate')
    def recalculate(self, request, id=None):
        if not InOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})

        if hasattr(request.user, 'supportmember'):

            order = InOrder.objects.get(id=id)
            support_member = request.user.supportmember

            if order.solution.merchant not in support_member.controlled_merchants.all():
                return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'This order is not under your control!'})

            serializer = RecalculateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)

            serializer_data = serializer.validated_data

            if serializer_data['amount'] == order.amount:
                return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Amount has not changed'})

            order.support_recalculate(serializer_data['amount'])

        elif hasattr(request.user, 'trader'):
            order = InOrder.objects.get(id=id)
            trader = request.user.trader

            if order.payment_details.group.trader != trader and order.payment_details.group.trader.boss != trader:
                return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'This order is not under your control!'})

            serializer = RecalculateSerializer(data=request.data)

            if not serializer.is_valid():
                return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)

            serializer_data = serializer.validated_data

            if serializer_data['amount'] == order.amount:
                return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Amount has not changed'})

            order.trader_recalculate(serializer_data['amount'])

        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='callback')
    def callback(self, request, id=None):
        in_order = InOrder.objects.get(id=id)

        support = request.user.supportmember

        if in_order.solution.merchant not in support.controlled_merchants.all():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'This order is not under your control!'})
        pay_in = in_order.pay_in.get()
        current_status = pay_in.status.name

        status_code = pay_in.send_callback({"status": current_status})

        return Response(status=status.HTTP_200_OK, data={'error': f'Status code: {status_code}'})

    @action(detail=False, methods=['GET'], permission_classes=[IsAuthenticated], url_path='export')
    def export_orders(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        status_filter = (request.query_params.get('status__name__in') or '').strip()
        status_names = [s.strip() for s in status_filter.split(',') if s.strip()]
        if status_names and 'Cannot process' not in status_names:
            queryset = queryset.exclude(status__name="Cannot process")

        for_merchant = hasattr(request.user, 'merchant') or hasattr(request.user, 'submerchant')
        return orders_excel_http_response(queryset, filename_prefix="orders_in", for_merchant=for_merchant)

    @action(detail=False, methods=['GET'], permission_classes=[TraderPermission], url_path='reasons')
    def get_reasons(self, request):
        data = [{"name": reason[0]} for reason in InOrder.REJECTION_CHOICES]
        return Response(status=status.HTTP_200_OK, data=data)


class OutOrderFilter(django_filters.FilterSet):
    class Meta:
        model = OutOrder
        fields = {
            'id': ['exact'],
            'creation_date': ['range'],
            'first_creation_date': ['range'],
            'payment_details__group__trader__user__username': ['in'],
            'payment_details__group__trader__team__name': ['in'],
            'status__name': ['in'],
            'amount': ['lte', 'gte'],
            'usd_amount': ['lte', 'gte'],
            'solution__payment_system__currency__symbol': ['in'],
            'solution__payment_system__name': ['in'],
            'solution__merchant__user__username': ['in'],
            'solution__traffic__name': ['in'],
            'payment_details__id': ['exact'],
            'payment_details__group__owner': ['icontains'],
            'payment_details__group__id': ['exact'],
            'payment_details__card_number': ['exact'],
            'merchant_order_id': ['exact'],
            'pay_out__client__client_id': ['exact'],
        }


class OutOrderViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = OutOrderFilter
    filterset_fields = ['creation_date', 'first_creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'solution', 'payment_details']
    search_fields = ['creation_date', 'first_creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'solution', 'payment_details']
    ordering_fields = ['creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'solution', 'payment_details']
    pagination_class = StandardResultsSetPagination
    http_method_names = ['get', 'post']
    ordering = ['-creation_date']

    def get_queryset(self):
        if hasattr(self.request.user, 'trader'):
            trader: Trader = self.request.user.trader
            if self.request.user.trader.is_boss:
                orders = OutOrder.objects.filter(payment_details__group__trader__team=trader.team)
            else:
                orders = OutOrder.objects.filter(payment_details__group__trader=trader)
            return orders

        if hasattr(self.request.user, 'supportmember'):
            support_member: SupportMember = self.request.user.supportmember

            if support_member.is_head:
                return OutOrder.objects.all()

            merchants = support_member.controlled_merchants.all()
            teams = support_member.controlled_teams.all()

            query = Q()
            if teams.exists():
                query &= Q(payment_details__group__trader__team__in=teams)
            if merchants.exists():
                query &= Q(solution__merchant__in=merchants)

            orders = OutOrder.objects.filter(query) if query else OutOrder.objects.none()
            return orders

        if hasattr(self.request.user, 'merchant'):
            merchant: Merchant = self.request.user.merchant
            orders = OutOrder.objects.filter(solution__merchant=merchant)
            return orders

        if hasattr(self.request.user, 'submerchant'):
            merchant: Merchant = self.request.user.submerchant.merchant
            orders = OutOrder.objects.filter(solution__merchant=merchant)
            return orders

        if hasattr(self.request.user, 'teamlead'):
            from trade.agent_commission import merchant_ids_for_agent
            from trade.teamlead_scope import teamlead_order_scope

            teamlead = self.request.user.teamlead
            if teamlead_order_scope(self.request) == 'merchant':
                merchant_ids = merchant_ids_for_agent(teamlead)
                return OutOrder.objects.filter(solution__merchant_id__in=merchant_ids)

            teams = TraderTeam.objects.filter(teamlead=teamlead)
            orders = OutOrder.objects.filter(payment_details__group__trader__team__in=teams)
            return orders

        return OutOrder.objects.none()

    def get_serializer_class(self):
        if hasattr(self.request.user, 'trader'):
            if self.request.user.trader.is_boss:
                if self.action == 'list':
                    return OutOrderTraderBossListSerializer
                else:
                    return OutOrderTraderBossFullSerializer
            else:
                if self.action == 'list':
                    return OutOrderTraderListSerializer
                else:
                    return OutOrderTraderFullSerializer
        if hasattr(self.request.user, 'merchant') or hasattr(self.request.user, 'submerchant'):
            if self.action == 'list':
                return OutOrderMerchantListSerializer
            else:
                return OutOrderMerchantSerializer
        if hasattr(self.request.user, 'teamlead'):
            from trade.teamlead_scope import teamlead_order_scope

            if teamlead_order_scope(self.request) == 'merchant':
                return OutOrderAgentMerchantSerializer
            return OutOrderTeamLeadSerializer
        if hasattr(self.request.user, 'supportmember'):
            if self.action == 'list':
                return OutOrderSupportListSerializer
            else:
                return OutOrderSupportSerializer
        return OutOrderTraderListSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.exclude(status__name__in=["Cannot process", "Failed"])

        completed = queryset.filter(status__name="Completed")
        total_usd_amount = completed.aggregate(sum_usd_amount=Sum('usd_amount'))['sum_usd_amount'] or 0

        if hasattr(self.request.user, 'merchant'):
            total_commission = completed.aggregate(sum_usd_amount=Sum('merchant_fee'))['sum_usd_amount'] or 0
            holded_orders = queryset.filter(status__name__in=['New', 'Arbitrage', 'Money sent by trader', 'Recalculation'])
            hold = holded_orders.aggregate(sum_usd_amount=Sum('usd_amount'))['sum_usd_amount'] or 0
        elif hasattr(self.request.user, 'support'):
            total_commission_merchant = completed.aggregate(sum_usd_amount=Sum('merchant_fee'))['sum_usd_amount'] or 0
            total_commission_trader = completed.aggregate(sum_usd_amount=Sum('trader_fee'))['sum_usd_amount'] or 0
            total_commission = total_commission_merchant - total_commission_trader
            hold = Decimal(0)
        elif hasattr(self.request.user, 'teamlead'):
            from trade.teamlead_scope import teamlead_order_scope

            if teamlead_order_scope(self.request) == 'merchant':
                total_commission = completed.aggregate(sum_usd_amount=Sum('agent_fee'))['sum_usd_amount'] or 0
                hold = Decimal(0)
            else:
                total_commission = completed.aggregate(sum_usd_amount=Sum('trader_fee'))['sum_usd_amount'] or 0
                hold = Decimal(0)
        else:
            total_commission = completed.aggregate(sum_usd_amount=Sum('trader_fee'))['sum_usd_amount'] or 0
            hold = Decimal(0)

        response = super().list(request, *args, **kwargs)

        response.data['total_usd_amount'] = total_usd_amount
        response.data['total_commission'] = total_commission
        response.data['hold'] = hold

        return response

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[TraderPermission | DebugPermission], url_path='money-sent')
    def money_sent(self, request, id=None):
        if not OutOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
        order = OutOrder.objects.get(id=id)

        order.money_sent()

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[TraderPermission | DebugPermission], url_path='cannot-process')
    def cannot_process(self, request, id=None):
        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer_data = serializer.validated_data
        if not OutOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
        order = OutOrder.objects.get(id=id)

        order.cannot_process(reason=serializer_data.get("trader_comment", ""))

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='cancel')
    def cancel(self, request, id=None):
        if not OutOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})

        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support'})

        order = OutOrder.objects.get(id=id)
        support_member = request.user.supportmember

        if order.payment_details.group.trader.team not in support_member.controlled_teams.all():
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'This order is not under your control!'})

        order.cancel_support()

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='reset')
    def reset(self, request, id=None):
        if not OutOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})

        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support'})

        order = OutOrder.objects.get(id=id)
        support_member = request.user.supportmember

        if order.payment_details.group.trader.team not in support_member.controlled_teams.all():
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'This order is not under your control!'})

        order.reset()

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission])
    def arbitrage(self, request, id=None):
        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})

        support: SupportMember = request.user.supportmember

        if not OutOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
        order = OutOrder.objects.get(id=id)

        if order.payment_details.group.trader.team not in support.controlled_teams.all():
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'It is not your order!'})

        order.arbitrage()

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='complete-support')
    def complete_support(self, request, id=None):
        if not OutOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})

        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'You are not from support'})

        order = OutOrder.objects.select_for_update().get(id=id)
        if order.status.name == "Completed":
            return Response(status=status.HTTP_409_CONFLICT, data={'error': 'Order already completed'})
        support_member = request.user.supportmember

        if order.payment_details.group.trader.team not in support_member.controlled_teams.all():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'This order is not under your control!'})

        order.complete_after_arbitrage()

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[TraderPermission | DebugPermission], url_path='complete-trader')
    def complete_trader(self, request, id=None):

        trader: Trader = request.user.trader

        if not OutOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
        order = OutOrder.objects.select_for_update().get(id=id)
        if order.status.name == "Completed":
            return Response(status=status.HTTP_409_CONFLICT, data={'error': 'Order already completed'})

        if order.payment_details.group.trader != trader:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'It is not your order!'})

        file = request.data.get('file')
        if not file:
            raise ValidationError("No file provided")

        # if file.content_type  == 'application/pdf':
        #     return Response({'error': 'Only PDFs are allowed.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer_data = OutOrderCheckSerializer(order).data
        result = send_to_fastapi(serializer_data, file)
        order.money_sent()
        order.add_pdf(result.get('file_url'), result.get('success'), result.get('comment'))

        return Response(status=status.HTTP_200_OK)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[MerchantPermission | DebugPermission])
    def complete(self, request, id=None):
        if not hasattr(request.user, 'merchant'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not a merchant!'})
        if not OutOrder.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})
        order = OutOrder.objects.select_for_update().get(id=id)
        if order.status.name == "Completed":
            return Response(status=status.HTTP_409_CONFLICT, data={'error': 'Order already completed'})
        merchant: Merchant = request.user.merchant

        if order.merchant != merchant:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'It is not your order!'})

        if order.status.name == "Arbitrage":
            order.complete_after_arbitrage()
        elif order.status.name == "Money sent by trader":
            order.complete_after_money_sent()
        else:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'Order cannot be completed!'})

        return Response(status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    @transaction.atomic
    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | TraderPermission | DebugPermission], url_path='recalculate')
    def recalculate(self, request, id=None):
        order = OutOrder.objects.get(id=id)

        if hasattr(request.user, 'trader'):
            serializer = RecalculateTraderSerializer(data=request.data)
        else:
            serializer = RecalculateSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)

        serializer_data = serializer.validated_data

        if serializer_data['amount'] == order.amount:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'error': 'Amount has not changed'})
        new_amount = serializer_data['amount']
        if hasattr(request.user, 'trader'):
            trader: Trader = request.user.trader

            if order.payment_details.group.trader != trader:
                return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'It is not your order!'})

            file = serializer_data['file']

            serializer_data = OutOrderCheckSerializer(order).data
            result = send_to_fastapi(serializer_data, file)
            order.pic = result.get('file_url')
            order.save()

            order.trader_recalculation(new_amount)
            return Response(status=status.HTTP_200_OK)

        if not hasattr(request.user, 'supportmember'):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support'})

        support_member = request.user.supportmember

        if order.solution.merchant not in support_member.controlled_merchants.all():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'This order is not under your control!'})

        order.recalculate(serializer_data['amount'])

        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], permission_classes=[SupportPermission | DebugPermission], url_path='callback')
    def callback(self, request, id=None):
        out_order = OutOrder.objects.get(id=id)

        support = request.user.supportmember

        if out_order.solution.merchant not in support.controlled_merchants.all():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'This order is not under your control!'})

        pay_out = PayOut.objects.get(merchant_order_id=out_order.merchant_order_id)
        current_status = pay_out.status.name

        status_code = pay_out.send_callback({"status": current_status})

        return Response(status=status.HTTP_200_OK, data={'details': f'Status code: {status_code}'})

    @action(detail=False, methods=['GET'], permission_classes=[TraderPermission], url_path='reasons')
    def get_reasons(self, request):
        data = [{"name": reason[0]} for reason in OutOrder.REJECTION_CHOICES]
        return Response(status=status.HTTP_200_OK, data=data)

    @action(detail=False, methods=['GET'], permission_classes=[IsAuthenticated], url_path='export')
    def export_orders(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.exclude(status__name__in=["Cannot process", "Failed"])

        for_merchant = hasattr(request.user, 'merchant') or hasattr(request.user, 'submerchant')
        return orders_excel_http_response(
            queryset,
            filename_prefix="orders_out",
            for_merchant=for_merchant,
            payment_fk_id_field='pay_out__id',
        )


class TraderTeamRatesViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = TraderTeamRates.objects.all()
    serializer_class = TraderTeamRatesSerializer
    permission_classes = [HeadSupportPermission | DebugPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'supportmember'):
            if user.supportmember.is_head:
                return TraderTeamRates.objects.all()
        elif hasattr(user, 'trader'):
            return TraderTeamRates.objects.filter(team=user.trader.team)
        else:
            return TraderTeamRates.objects.none()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = TraderTeamRatesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

