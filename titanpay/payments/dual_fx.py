"""Два курса на KZT pay-in: мерчанту xe+N, PSP свой xe+M. Контрагентам чужой курс не отдаём."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from basics.utils import xe_kzt_markup_for_ps

logger = logging.getLogger(__name__)
TWOPLACES = Decimal("0.01")
RATEPLACES = Decimal("0.001")

# Тетрадь условий: курс PSP vs мерч xe+5. Ставки in — shell_apply_psp_kzt_terms.py
_PSP_USERNAME_SETTINGS = (
    ("PAYPLAT_TRADER_USERNAME", "payplat1"),
    ("PATRIOTPAY_TRADER_USERNAME", "patriot1"),
    ("GIPAY_TRADER_USERNAME", "gipay1"),
    ("VISIONX_TRADER_USERNAME", "visionx1"),
    ("LAYERONE_TRADER_USERNAME", "layerone1"),
    ("PROCHUB_TRADER_USERNAME", "prochub1"),
    ("NEXUS_TRADER_USERNAME", "nexus1"),
    ("PLUTUS_TRADER_USERNAME", "plutus1"),
    ("BITZONE_TRADER_USERNAME", "bitzone1"),
)


@dataclass(frozen=True)
class DualFxQuote:
    merchant_rate: Decimal
    psp_rate: Decimal
    merchant_usd: Decimal
    psp_usd: Decimal
    merchant_markup: Decimal
    psp_markup: Decimal


def _dec(raw) -> Decimal:
    return Decimal(str(raw))


def _usd(amount: Decimal, rate: Decimal) -> Decimal:
    if rate <= 0:
        return Decimal("0")
    return (amount / rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def is_kzt_payment_system(payment_system) -> bool:
    currency = getattr(payment_system, "currency", None)
    symbol = (getattr(currency, "symbol", None) or "").upper()
    if symbol == "KZT":
        return True
    name = (getattr(payment_system, "name", None) or "").upper()
    return "KZT" in name


def merchant_fx_markup(payment_system) -> Decimal:
    name = getattr(payment_system, "name", None) if payment_system is not None else None
    return xe_kzt_markup_for_ps(name)


def _psp_markup_map() -> dict[str, Decimal]:
    from django.conf import settings

    raw = getattr(settings, "PSP_XE_MARKUP_BY_TRADER", None) or ""
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(str(raw)) if str(raw).strip() else {}
        except Exception:
            logger.warning("PSP_XE_MARKUP_BY_TRADER is not valid JSON")
            return {}
    out = {}
    for key, val in (data or {}).items():
        try:
            out[str(key).strip().lower()] = _dec(val)
        except Exception:
            continue
    return out


def _canonical_trader_key(trader) -> str:
    from django.conf import settings

    user = getattr(trader, "user", None)
    uname = (getattr(user, "username", None) or "").strip().lower()
    aliases = {uname: uname}
    for setting_name, default in _PSP_USERNAME_SETTINGS:
        configured = (getattr(settings, setting_name, default) or default).strip().lower()
        aliases[configured] = default
        aliases[default] = default
    return aliases.get(uname, uname)


def psp_fx_markup_for_trader(trader, *, fallback: Decimal) -> Decimal:
    if trader is None:
        return fallback
    key = _canonical_trader_key(trader)
    mapped = _psp_markup_map().get(key)
    return mapped if mapped is not None else fallback


def _bitzone_p2p_rate(trader) -> Decimal | None:
    if trader is None:
        return None
    if _canonical_trader_key(trader) != "bitzone1":
        return None
    from basics.utils import get_binance_kzt_kaspi_rate

    return get_binance_kzt_kaspi_rate()


def quote_dual_fx(*, amount, payment_system, trader=None) -> DualFxQuote:
    amount = _dec(amount)
    merchant_rate = _dec(payment_system.get_rate())
    merchant_usd = _usd(amount, merchant_rate)
    merchant_markup = merchant_fx_markup(payment_system)
    if (
        not is_kzt_payment_system(payment_system)
        or trader is None
        or merchant_rate <= 0
        or merchant_markup <= 0
    ):
        return DualFxQuote(
            merchant_rate=merchant_rate,
            psp_rate=merchant_rate,
            merchant_usd=merchant_usd,
            psp_usd=merchant_usd,
            merchant_markup=merchant_markup,
            psp_markup=merchant_markup,
        )
    p2p_rate = _bitzone_p2p_rate(trader)
    if p2p_rate is not None and p2p_rate > 0:
        psp_rate = _dec(p2p_rate).quantize(RATEPLACES, rounding=ROUND_HALF_UP)
        xe_base = (merchant_rate / merchant_markup) if merchant_markup else merchant_rate
        psp_markup = (psp_rate / xe_base).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if xe_base else merchant_markup
        psp_usd = _usd(amount, psp_rate)
        return DualFxQuote(
            merchant_rate=merchant_rate,
            psp_rate=psp_rate,
            merchant_usd=merchant_usd,
            psp_usd=psp_usd,
            merchant_markup=merchant_markup,
            psp_markup=psp_markup,
        )
    psp_markup = psp_fx_markup_for_trader(trader, fallback=merchant_markup)
    psp_rate = (merchant_rate * psp_markup / merchant_markup).quantize(RATEPLACES, rounding=ROUND_HALF_UP)
    if psp_rate <= 0:
        psp_rate = merchant_rate
    psp_usd = _usd(amount, psp_rate)
    return DualFxQuote(
        merchant_rate=merchant_rate,
        psp_rate=psp_rate,
        merchant_usd=merchant_usd,
        psp_usd=psp_usd,
        merchant_markup=merchant_markup,
        psp_markup=psp_markup,
    )


def apply_dual_fx_to_order(order, trader, *, amount=None, payment_system=None) -> DualFxQuote:
    amount = order.amount if amount is None else amount
    ps = payment_system
    if ps is None:
        solution = getattr(order, "solution", None)
        ps = getattr(solution, "payment_system", None) if solution is not None else None
    quote = quote_dual_fx(amount=amount, payment_system=ps, trader=trader)
    order.merchant_rate = quote.merchant_rate
    order.psp_rate = quote.psp_rate
    order.psp_usd_amount = quote.psp_usd
    return quote


def order_merchant_rate(order) -> Decimal | None:
    stored = getattr(order, "merchant_rate", None)
    if stored:
        return _dec(stored)
    return None


def order_psp_usd(order) -> Decimal:
    raw = getattr(order, "psp_usd_amount", None)
    if raw:
        return _dec(raw)
    return _dec(getattr(order, "usd_amount", 0) or 0)


def expose_usd_amount(payload: dict, order, *, audience: str) -> dict:
    """audience=merchant — usd мерчанта; psp — usd провайдера/трейдера. Чужой курс в payload не кладём."""
    if audience == "psp":
        payload["usd_amount"] = float(order_psp_usd(order))
        payload.pop("merchant_rate", None)
        payload.pop("psp_rate", None)
        payload.pop("fx_spread_usd", None)
    else:
        payload["usd_amount"] = float(_dec(getattr(order, "usd_amount", 0) or 0))
        payload.pop("psp_rate", None)
        payload.pop("psp_usd_amount", None)
        payload.pop("fx_spread_usd", None)
    return payload


def merchant_visible_rate(pay_in) -> Any:
    """Только курс мерчанта (зафиксированный на ордере или PS). PSP-курс сюда не попадает."""
    order = getattr(pay_in, "order", None)
    stored = order_merchant_rate(order) if order is not None else None
    if stored is not None:
        return stored
    return None
