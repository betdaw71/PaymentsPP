"""Курс и комиссия сделки в create pay-in / callback — точечно по мерчантам."""
from decimal import Decimal

from merchant.tiered_mdr import effective_mdr_in
from payments.merchant_usd_amount import ALEMKREDIT_USERNAME

AGGREPAY_USERNAME = "aggrepay"


def _as_float(value):
    if value is None:
        return None
    return float(Decimal(str(value)))


def _merchant_username(pay_in) -> str:
    merchant = getattr(pay_in, "merchant", None)
    if merchant is None:
        order = getattr(pay_in, "order", None)
        solution = getattr(order, "solution", None) if order is not None else None
        merchant = getattr(solution, "merchant", None) if solution is not None else None
    user = getattr(merchant, "user", None)
    return (getattr(user, "username", None) or "").strip()


def is_aggrepay_merchant(pay_in) -> bool:
    return _merchant_username(pay_in).lower() == AGGREPAY_USERNAME


def is_alemkredit_payin(pay_in) -> bool:
    return _merchant_username(pay_in).lower() == ALEMKREDIT_USERNAME


def _deal_rate(pay_in):
    order = getattr(pay_in, "order", None)
    detail = getattr(order, "payment_details", None) if order is not None else None
    group = getattr(detail, "group", None) if detail is not None else None
    ps = getattr(group, "payment_system", None) if group is not None else None
    if ps is None and order is not None:
        solution = getattr(order, "solution", None)
        ps = getattr(solution, "payment_system", None) if solution is not None else None
    if ps is None:
        ps = getattr(pay_in, "payment_system", None)
    if ps is None:
        return None
    return ps.get_rate()


def deal_quote_fields(pay_in) -> dict:
    order = getattr(pay_in, "order", None)
    if order is None:
        return {}

    if is_aggrepay_merchant(pay_in):
        solution = getattr(order, "solution", None)
        fee_percent = effective_mdr_in(solution, order.amount) if solution is not None else None
        return {
            "rate": _as_float(_deal_rate(pay_in)),
            "fee": _as_float(getattr(order, "merchant_fee", None)),
            "fee_percent": _as_float(fee_percent),
        }

    if is_alemkredit_payin(pay_in):
        rate = _deal_rate(pay_in)
        if rate is None:
            return {}
        return {"rate": _as_float(rate)}

    return {}


def callback_extra_fields(pay_in) -> dict:
    """Доп. поля webhook: курс — только Alemkredit."""
    if not is_alemkredit_payin(pay_in):
        return {}
    rate = _deal_rate(pay_in)
    if rate is None:
        return {}
    return {"rate": _as_float(rate)}


def apply_deal_quote(representation, pay_in):
    representation.update(deal_quote_fields(pay_in))
    return representation
