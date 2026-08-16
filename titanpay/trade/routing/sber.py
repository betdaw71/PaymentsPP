from merchant.models import Merchant, MerchantSolution
from basics.models import PaymentDetails, PaymentSystem, Trader, PaymentDetailsGroup, TrafficType
from rest_framework.exceptions import ValidationError
from django.db.models import F, ExpressionWrapper, DecimalField, Q
import random
import re
from decimal import Decimal

from trade.routing.routeutils import get_teams_for_ps
from payments.psp_payin import psp_trader_usernames


class SberRouting:
    def get_possible_options_in(self, risk_cluster, payment_system: PaymentSystem, amount, traffic_type: TrafficType, usd_amount):
        teams = get_teams_for_ps(payment_system)
        psp_users = psp_trader_usernames()
        groups_base = PaymentDetailsGroup.objects.filter(work_type="by_card", trader__team__in=teams)
        # PSP и обычные трейдеры: available >= usd_amount (freeze при создании InOrder).
        balance_ok = Q(trader__balance_usdt__amount__gte=usd_amount)
        possible_options = groups_base.filter(balance_ok).filter(
            status=1,
            payment_system=payment_system,
            allowed_traffic=traffic_type,
            in_active=True,
            trader__blocked=False,
        )

        filtered_options = possible_options.annotate(
            total_value=ExpressionWrapper(
                F("current_volume") + amount,
                output_field=DecimalField(max_digits=32, decimal_places=2),
            )
        ).filter(Q(total_value__lte=F("limit_per_period")) | Q(trader__user__username__in=psp_users))
        return filtered_options
    
    def get_details(self, possible_options, active_orders, amount, merchant=None):
        from payments.psp_payin import is_psp_trader, sort_groups_for_routing
        from merchant.kzt_settlement import melbet_kzt_test_trader_username

        chosen_group = sort_groups_for_routing(
            possible_options.select_related("trader", "trader__user", "trader__team", "payment_system"),
            amount,
        )

        preferred = melbet_kzt_test_trader_username(merchant)
        if preferred:
            pref = [g for g in chosen_group if g.trader.user.username == preferred]
            if pref:
                chosen_group = pref + [g for g in chosen_group if g.trader.user.username != preferred]

        active_details = PaymentDetails.objects.filter(inorders__in=active_orders)

        for group in chosen_group:
            available_details = PaymentDetails.objects.filter(
                group=group,
                status=1,
                sberpay_enabled=False,
                sbp_enabled=False,
                card_number__isnull=False,
            )
            # PSP (ExpayOne/FairPay): одна виртуальная карта, реквизит уникален на PayIn — не блокировать по сумме.
            if not is_psp_trader(group.trader):
                available_details = available_details.exclude(id__in=active_details)
            if available_details.exists():
                chosen_detail = available_details.order_by('?').first()

                return chosen_detail

        return None

    def check_cluster(self, risk_cluster, payment_system, amount, active_orders, traffic_type, usd_amount):
        options = self.get_possible_options_in(risk_cluster, payment_system, amount, traffic_type, usd_amount)

        chosen_detail = self.get_details(options, active_orders, amount, merchant=merchant)

        if chosen_detail is not None:
            return chosen_detail

        return None

    def choose_detail_in(self, amount: Decimal, usd_amount: Decimal, payment_system: PaymentSystem, traffic_type: TrafficType, active_orders,
                         client_deposit_count, merchant=None):

        possible_options = self.get_possible_options_in(None, payment_system, amount, traffic_type, usd_amount)

        chosen_detail = self.get_details(possible_options, active_orders, amount, merchant=merchant)

        if chosen_detail is not None:
            return chosen_detail

        return None

    def get_possible_options_out(self, payment_system: PaymentSystem, traffic_type: TrafficType, amount, excluded):

        possible_groups = PaymentDetailsGroup.objects.filter(status=1, payment_system=payment_system, out_active=True, min_amount_out__lte=amount, max_amount_out__gte=amount, amount__gte=amount, trader__blocked=False, allowed_traffic=traffic_type, deposit_number_on=False)

        possible_groups = possible_groups.exclude(trader__in=excluded)

        return possible_groups.order_by('current_out_volume')

    def choose_detail_out(self, amount: Decimal, payment_system: PaymentSystem, traffic_type: TrafficType, excluded=None, merchant=None):
        if excluded is None:
            excluded = list()

        possible_options = self.get_possible_options_out(payment_system, traffic_type, amount, excluded)
        if not possible_options.exists():
            return None

        groups = list(possible_options)
        from merchant.kzt_settlement import melbet_kzt_test_trader_username

        preferred = melbet_kzt_test_trader_username(merchant)
        if preferred:
            pref = [g for g in groups if g.trader.user.username == preferred]
            if pref:
                groups = pref + [g for g in groups if g.trader.user.username != preferred]

        for group in groups:
            chosen_detail = PaymentDetails.objects.filter(group=group, status=1, sberpay_enabled=False, sbp_enabled=False, card_number__isnull=False).order_by('?').first()
            if chosen_detail is not None:
                return chosen_detail

        return None