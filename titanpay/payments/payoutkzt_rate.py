"""XE.com USD/KZT rate used only for PayPlat payouts (PAYOUTKZT)."""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "payoutkzt_xe_rate"


def payoutkzt_ps_name() -> str:
    return (getattr(settings, "PAYOUTKZT_PS_NAME", None) or "PAYOUTKZT").strip() or "PAYOUTKZT"


def payoutkzt_xe_markup() -> Decimal:
    """Payouts use raw XE mid-market. Optional override: XE_KZT_MARKUP_BY_PS.PAYOUTKZT."""
    from basics.utils import _xe_kzt_markup_map

    by_ps = _xe_kzt_markup_map()
    name = payoutkzt_ps_name()
    if name in by_ps:
        return by_ps[name]
    return Decimal("1")


def cache_payoutkzt_rate(rate: Decimal) -> None:
    try:
        cache.set(CACHE_KEY, str(rate), timeout=15 * 60)
    except Exception:
        logger.warning("PAYOUTKZT cache set failed", exc_info=True)


def store_payoutkzt_rate(rate: Decimal) -> None:
    """Persist XE payout rate on PS PAYOUTKZT (in/out off — not used for pay-in)."""
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


def fetch_payoutkzt_xe_quote() -> dict | None:
    """Live XE USD/KZT mid-market (no pay-in markup)."""
    from basics.utils import get_xe_kzt_base_rate

    base = get_xe_kzt_base_rate()
    if base is None or base <= 0:
        return None
    markup = payoutkzt_xe_markup()
    rate = (base * markup).quantize(Decimal("0.001"))
    return {
        "rate": rate,
        "base": base,
        "markup": markup,
        "source": "xe",
    }


def get_payoutkzt_rate(*, live: bool = False) -> Decimal | None:
    """Stored XE rate for PayPlat payouts. live=True hits xe.com now and stores."""
    if live:
        quote = fetch_payoutkzt_xe_quote()
        if quote is not None:
            store_payoutkzt_rate(quote["rate"])
            return quote["rate"]
        return None

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

    quote = fetch_payoutkzt_xe_quote()
    if quote is not None:
        store_payoutkzt_rate(quote["rate"])
        return quote["rate"]
    return None
