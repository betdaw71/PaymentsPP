"""Bybit Kaspi USDT/KZT rate used only for PayPlat payouts (PAYOUTKZT)."""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "payoutkzt_bybit_rate"


def payoutkzt_ps_name() -> str:
    return (getattr(settings, "PAYOUTKZT_PS_NAME", None) or "PAYOUTKZT").strip() or "PAYOUTKZT"


def cache_payoutkzt_rate(rate: Decimal) -> None:
    try:
        cache.set(CACHE_KEY, str(rate), timeout=15 * 60)
    except Exception:
        logger.warning("PAYOUTKZT cache set failed", exc_info=True)


def store_payoutkzt_rate(rate: Decimal) -> None:
    """Persist Bybit payout rate on PS PAYOUTKZT (in/out off — not used for pay-in)."""
    from basics.models import Currency, PaymentSystem

    if rate is None or rate <= 0:
        return
    cache_payoutkzt_rate(rate)
    kzt = Currency.objects.filter(symbol__iexact="KZT").first()
    if kzt is None:
        return
    name = payoutkzt_ps_name()
    ps = PaymentSystem.objects.filter(name__iexact=name, currency=kzt).first()
    if ps is None:
        ps = PaymentSystem.objects.create(
            name=name,
            currency=kzt,
            required_fields={},
            usdt_exchange_rate=rate,
            in_on=False,
            out_on=False,
        )
        ps.update_rate(rate)
        logger.info("PAYOUTKZT payment system created id=%s rate=%s", ps.id, rate)
        return
    fields = []
    if ps.in_on:
        ps.in_on = False
        fields.append("in_on")
    if ps.out_on:
        ps.out_on = False
        fields.append("out_on")
    if fields:
        ps.save(update_fields=fields)
    ps.update_rate(rate)


def get_payoutkzt_rate(*, live: bool = False) -> Decimal | None:
    """Stored Bybit rate for PayPlat payouts. live=True hits Bybit now and stores."""
    from basics.utils import get_bybit_kzt_rate

    if live:
        rate = get_bybit_kzt_rate()
        if rate is not None:
            store_payoutkzt_rate(rate)
        return rate

    from basics.models import PaymentSystem

    ps = PaymentSystem.objects.filter(name__iexact=payoutkzt_ps_name(), currency__symbol__iexact="KZT").first()
    if ps is not None:
        rate = ps.get_rate()
        if rate and rate > 0:
            return Decimal(str(rate))

    cached = None
    try:
        cached = cache.get(CACHE_KEY)
    except Exception:
        cached = None
    if cached:
        try:
            val = Decimal(str(cached))
            if val > 0:
                return val
        except Exception:
            pass

    rate = get_bybit_kzt_rate()
    if rate is not None:
        store_payoutkzt_rate(rate)
    return rate
