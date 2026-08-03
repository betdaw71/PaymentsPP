from merchant.models import Merchant, MerchantSolution
from basics.models import PaymentDetails, PaymentSystem, Trader, PaymentDetailsGroup, TrafficType
from rest_framework.exceptions import ValidationError
from django.db.models import F, ExpressionWrapper, DecimalField
import random
import re
from decimal import Decimal

from trade.routing.routeutils import get_teams_for_ps


class SberRouting:

    def get_possible_options_in(self, risk_cluster, payment_system: PaymentSystem, amount, traffic_type: TrafficType,
                                usd_amount):
        teams = get_teams_for_ps(payment_system)
        groups_with_sufficient_balance = PaymentDetailsGroup.objects.filter(
            trader__balance_usdt__amount__gte=usd_amount, work_type='by_card', trader__team__in=teams)

        possible_options = groups_with_sufficient_balance.filter(status=1, payment_system=payment_system,
                                                                 allowed_traffic=traffic_type, in_active=True,
                                                                 trader__blocked=False)

        filtered_options = possible_options.annotate(
            total_value=ExpressionWrapper(F('current_volume') + amount,
                                          output_field=DecimalField(max_digits=32, decimal_places=2))
        ).filter(total_value__lte=F('limit_per_period'))

        return filtered_options

    def get_details(self, possible_options, active_orders):
        chosen_group = possible_options.order_by('current_volume')

        active_details = PaymentDetails.objects.filter(inorders__in=active_orders)

        for group in chosen_group:
            available_details = PaymentDetails.objects.filter(group=group, status=1, sberpay_enabled=False,
                                                              sbp_enabled=False, card_number__isnull=False).exclude(
                id__in=active_details)
            if available_details.exists():
                chosen_detail = available_details.order_by('?').first()

                return chosen_detail

        return None

    def check_cluster(self, risk_cluster, payment_system, amount, active_orders, traffic_type, usd_amount):
        options = self.get_possible_options_in(risk_cluster, payment_system, amount, traffic_type, usd_amount)

        chosen_detail = self.get_details(options, active_orders)

        if chosen_detail is not None:
            return chosen_detail

        return None

    def choose_detail_in(self, amount: Decimal, usd_amount: Decimal, payment_system: PaymentSystem,
                         traffic_type: TrafficType, active_orders,
                         client_deposit_count, merchant=None):

        possible_options = self.get_possible_options_in(None, payment_system, amount, traffic_type, usd_amount)

        chosen_detail = self.get_details(possible_options, active_orders)

        if chosen_detail is not None:
            return chosen_detail

        return None

    def get_possible_options_out(self, payment_system: PaymentSystem, traffic_type: TrafficType, amount, excluded):

        possible_groups = PaymentDetailsGroup.objects.filter(status=1, payment_system=payment_system, out_active=True,
                                                             min_amount_out__lte=amount, max_amount_out__gte=amount,
                                                             amount__gte=amount, trader__blocked=False,
                                                             allowed_traffic=traffic_type, deposit_number_on=False)

        possible_groups = possible_groups.exclude(trader__in=excluded)

        return possible_groups.order_by('current_out_volume')

    def choose_detail_out(self, amount: Decimal, payment_system: PaymentSystem, traffic_type: TrafficType,
                          excluded=None, merchant=None):
        if excluded is None:
            excluded = list()

        possible_options = self.get_possible_options_out(payment_system, traffic_type, amount, excluded)
        if not possible_options.exists():
            return None

        for group in possible_options:
            chosen_detail = PaymentDetails.objects.filter(group=group, status=1, sberpay_enabled=False,
                                                          sbp_enabled=False, card_number__isnull=False).order_by(
                '?').first()
            if chosen_detail is not None:
                return chosen_detail

        return None