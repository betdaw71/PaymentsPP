from merchant.models import Merchant, MerchantSolution
from basics.models import PaymentDetails, PaymentSystem, Trader, PaymentDetailsGroup, TrafficType, TraderTeamRates
from trade.routing.base import route
from rest_framework.exceptions import ValidationError
from django.db.models import F, ExpressionWrapper, DecimalField
import random
import re
from decimal import Decimal


def calculate_fees(amount, solution: MerchantSolution, trader: Trader, direction='in'):
    try:
        team_rate_obj = TraderTeamRates.objects.get(
            team=trader.team,
            payment_system=solution.payment_system,
        )
    except TraderTeamRates.DoesNotExist:
        raise ValidationError("Team rates not configured for this payment system")

    if direction == 'in':
        team_rate = team_rate_obj.mdr_in / Decimal(100)
        merchant_rate = solution.mdr_in / Decimal(100)

        for_trader = amount * team_rate
        for_merchant = amount - amount * merchant_rate

        for_platform = amount * (merchant_rate - team_rate)

    else:
        team_rate = team_rate_obj.mdr_out / Decimal(100)
        merchant_rate = solution.mdr_out / Decimal(100)

        for_trader = amount + amount * team_rate
        for_merchant = amount + amount * merchant_rate

        for_platform = amount * (merchant_rate - team_rate)

    if for_platform < 0:
        raise ValidationError("Fees are too low")

    return for_merchant, for_trader, for_platform


def choose_trader_in(amount: Decimal, payment_system: PaymentSystem, traffic_type: TrafficType, active_orders, client_deposit_count):
    router = route(payment_system)

    usd_amount = amount / payment_system.get_rate()

    chosen_detail = router.choose_detail_in(amount, usd_amount, payment_system, traffic_type, active_orders, client_deposit_count)

    if chosen_detail is None:
        return None, usd_amount, payment_system, False

    return chosen_detail, usd_amount, payment_system, True


def choose_trader_out(amount: Decimal, payment_system: PaymentSystem, traffic_type: TrafficType, excluded=None):
    router = route(payment_system)

    chosen_detail = router.choose_detail_out(amount, payment_system, traffic_type, excluded)

    usd_amount = amount / payment_system.get_rate()

    if chosen_detail is None:
        return None, usd_amount, False
    else:
        return chosen_detail, usd_amount, True


def check_details(payment_system: PaymentSystem, details):
    required_fields = payment_system.required_fields

    required_keys = set(payment_system.required_fields.keys())
    detail_keys = set(details.keys())

    missing_keys = required_keys - detail_keys
    extra_keys = detail_keys - required_keys

    if missing_keys:
        raise ValidationError({
            'details': f"Missing required fields for {payment_system.name}: {', '.join(missing_keys)}."
        })

    if extra_keys:
        raise ValidationError({
            'details': f"Extra fields present: {', '.join(extra_keys)}."
        })

    for key in required_keys:
        pattern = re.compile(required_fields.get(key).get('regex'))

        string_to_check = details.get(key)

        result = pattern.match(string_to_check)

        if not result:
            raise ValidationError({
                'details': f"Value {string_to_check} provided in field {key} does not match pattern {required_fields.get(key).get('pattern')}"
            })
    return True


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
