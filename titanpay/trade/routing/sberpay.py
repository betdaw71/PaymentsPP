from merchant.models import Merchant, MerchantSolution
from basics.models import PaymentDetails, PaymentSystem, Trader, PaymentDetailsGroup, TrafficType
from rest_framework.exceptions import ValidationError
from django.db.models import F, ExpressionWrapper, DecimalField
from titanpay.settings import SBER_NAME
import random
import re
from decimal import Decimal

from trade.routing.routeutils import get_teams_for_ps


class SberPayRouting:

    def __init__(self):
        self.value_bound_1 = 3000
        self.value_bound_2 = 20000
        self.volume_bound_1 = 100000
        self.volume_bound_2 = 500000

    def get_risks(self, client_deposit_count, traffic_type: TrafficType, amount):

        if client_deposit_count < 3:
            client_risk = 0
        elif client_deposit_count < 10:
            client_risk = 1
        else:
            client_risk = 2

        if amount < self.value_bound_1:
            value_risk = 0
        elif amount < self.value_bound_2:
            value_risk = 1
        else:
            value_risk = 2

        risk_sum = 0.5 * client_risk + 0.3 * traffic_type.risk_level + 0.2 * value_risk

        if risk_sum <= 0.6:
            return 0
        elif risk_sum <= 0.9:
            return 1
        else:
            return 2

    def get_possible_options(self, risk_cluster, payment_system: PaymentSystem, amount, usd_amount):
        groups_with_sufficient_balance = PaymentDetailsGroup.objects.filter(trader__balance_usdt__amount__gte=usd_amount)

        if risk_cluster == 0:
            bound = self.volume_bound_1
            possible_options = groups_with_sufficient_balance.filter(status=1, payment_system=payment_system,
                                                                  in_active=True,
                                                                  trader__blocked=False, total_volume__lte=bound)
        elif risk_cluster == 1:
            lower_bound = self.volume_bound_1
            upper_bound = self.volume_bound_2
            possible_options = groups_with_sufficient_balance.filter(status=1, payment_system=payment_system,
                                                                  in_active=True,
                                                                  trader__blocked=False, total_volume__lte=upper_bound,
                                                                  total_volume__gt=lower_bound)

        else:
            lower_bound = self.volume_bound_2
            possible_options = groups_with_sufficient_balance.filter(status=1, payment_system=payment_system,
                                                                  in_active=True,
                                                                  trader__blocked=False, total_volume__gt=lower_bound)

        filtered_options = possible_options.annotate(
            total_value=ExpressionWrapper(F('current_volume') + amount,
                                          output_field=DecimalField(max_digits=32, decimal_places=2))
        ).filter(total_value__lte=F('limit_per_period'))

        return filtered_options

    def get_details(self, possible_options, active_orders):
        chosen_group = possible_options.order_by('current_volume')

        active_details = PaymentDetails.objects.filter(inorders__in=active_orders, sberpay_enabled=True)

        for group in chosen_group:
            available_details = PaymentDetails.objects.filter(group=group, sberpay_enabled=True, status=1, phone__isnull=False).exclude(id__in=active_details)
            if available_details.exists():
                chosen_detail = available_details.order_by('?').first()

                return chosen_detail

        return None

    def check_cluster(self, risk_cluster, payment_system, amount, active_orders, usd_amount):
        options = self.get_possible_options(risk_cluster, payment_system, amount, usd_amount)

        chosen_detail = self.get_details(options, active_orders)

        if chosen_detail is not None:
            return chosen_detail

        return None

    def choose_detail_in(self, amount: Decimal, usd_amount: Decimal, payment_system: PaymentSystem, traffic_type: TrafficType, active_orders,
                         client_deposit_count, merchant=None):

        payment_system = PaymentSystem.objects.get(name=SBER_NAME)

        risk_cluster = initial_risk_cluster = self.get_risks(client_deposit_count, traffic_type, amount)

        possible_options = self.get_possible_options(risk_cluster, payment_system, amount, usd_amount)

        if not possible_options.exists() and risk_cluster < 2:
            risk_cluster += 1
            possible_options = self.get_possible_options(risk_cluster, payment_system, amount, usd_amount)

            if risk_cluster == 1 and not possible_options.exists():
                risk_cluster += 1
                possible_options = self.get_possible_options(risk_cluster, payment_system, amount, usd_amount)

                if not possible_options.exists():
                    return None

        chosen_detail = self.get_details(possible_options, active_orders)

        if chosen_detail is not None:
            return chosen_detail

        if initial_risk_cluster == risk_cluster == 0 or initial_risk_cluster == risk_cluster == 1:
            risk_cluster += 1
            chosen_detail = self.check_cluster(risk_cluster, payment_system, amount, active_orders, usd_amount)
            if chosen_detail is not None:
                return chosen_detail

        if initial_risk_cluster == risk_cluster == 2:
            risk_cluster = 1
            chosen_detail = self.check_cluster(risk_cluster, payment_system, amount, active_orders, usd_amount)
            if chosen_detail is not None:
                return chosen_detail

        if initial_risk_cluster == 0 and risk_cluster == 1:
            risk_cluster = 2
            chosen_detail = self.check_cluster(risk_cluster, payment_system, amount, active_orders, usd_amount)
            return chosen_detail

        if initial_risk_cluster == 1 and risk_cluster == 2 or initial_risk_cluster == 2 and risk_cluster == 1:
            risk_cluster = 0
            chosen_detail = self.check_cluster(risk_cluster, payment_system, amount, active_orders, usd_amount)
            return chosen_detail

        return None

    def choose_detail_out(self, amount: Decimal, payment_system: PaymentSystem, traffic_type: TrafficType,
                          excluded=None, merchant=None):
        raise ValidationError("This method does not support pay-outs!")
