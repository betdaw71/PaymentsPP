"""Политика обязательного чека на платёжной странице."""
from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist

from appeals.models import PayInAppeal, PayInAppealStatus
from merchant.kzt_settlement import is_melbet_merchant
from payments.models import PayIn

KZT_RECEIPT_PAYMENT_SYSTEMS = frozenset({"C2CKZT", "C2CKZTTEST"})


def _is_melbet_redirect_payin(pay_in: PayIn) -> bool:
    if is_melbet_merchant(getattr(pay_in, "merchant", None)):
        return True
    try:
        return getattr(pay_in, "melbet_session", None) is not None
    except ObjectDoesNotExist:
        return False


def receipt_required_for_payin(pay_in: PayIn) -> bool:
    # Melbet — hosted redirect: чек не обязателен, «Я оплатил» доступно сразу.
    if _is_melbet_redirect_payin(pay_in):
        return False
    currency = (pay_in.currency.symbol if pay_in.currency else "") or ""
    if currency.upper() == "KZT":
        return True
    ps_name = (pay_in.payment_system.name if pay_in.payment_system else "") or ""
    return ps_name in KZT_RECEIPT_PAYMENT_SYSTEMS


def has_receipt_for_payin(pay_in: PayIn) -> bool:
    order = pay_in.order
    if order and (order.pic or "").strip():
        return True
    return PayInAppeal.objects.filter(
        pay_in=pay_in,
        status__in=[
            PayInAppealStatus.CREATED,
            PayInAppealStatus.SENT_TO_PROVIDER,
            PayInAppealStatus.APPROVED,
        ],
    ).exclude(receipt_url="").exists()
