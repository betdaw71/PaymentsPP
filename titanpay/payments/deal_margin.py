"""Маржа площадки на pay-in: не выдавать трейдеру/PSP, если зазор < минимума.

PnL (USDT) = merchant_fee + FX_spread − trader_fee − agent_fee
  FX_spread = psp_usd − merchant_usd
  teamlead_share = merchant_usd × TL% / 100  (% от оборота; режется с трейдера, не доп. расход площадки;
                  в разборе показываем отдельно)

Минимум: DEAL_MARGIN_MIN_PCT % от merchant_usd (дефолт 0.2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

logger = logging.getLogger(__name__)

TWOPLACES = Decimal("0.01")
PCTPLACES = Decimal("0.0001")
DEFAULT_MIN_PCT = Decimal("0.2")


def _d(raw) -> Decimal:
    return Decimal(str(raw or 0))


def _money(raw) -> Decimal:
    return _d(raw).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def deal_margin_filter_enabled() -> bool:
    from django.conf import settings

    raw = getattr(settings, "DEAL_MARGIN_FILTER_ENABLED", "1")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def deal_margin_min_pct() -> Decimal:
    from django.conf import settings

    raw = getattr(settings, "DEAL_MARGIN_MIN_PCT", None)
    try:
        return Decimal(str(raw if raw not in (None, "") else DEFAULT_MIN_PCT))
    except Exception:
        return DEFAULT_MIN_PCT


@dataclass(frozen=True)
class DealMarginQuote:
    amount: Decimal
    merchant_usd: Decimal
    psp_usd: Decimal
    merchant_rate: Decimal
    psp_rate: Decimal
    merchant_mdr: Decimal
    trader_mdr: Decimal
    merchant_fee: Decimal
    trader_fee: Decimal
    agent_fee: Decimal
    teamlead_pct: Decimal
    teamlead_share: Decimal
    fx_spread: Decimal
    platform_pnl: Decimal
    platform_pct: Decimal
    min_pct: Decimal
    ok: bool

    def as_skip_reason(self) -> str:
        return (
            f"margin_low pnl={self.platform_pnl} "
            f"pct={self.platform_pct}% < min={self.min_pct}%"
        )


def _resolve_solution(merchant, payment_system, *, amount=None, ftd=None):
    from merchant.models import MerchantSolution

    if merchant is None or payment_system is None:
        return None
    qs = MerchantSolution.objects.filter(
        merchant=merchant,
        payment_system=payment_system,
        status=1,
    ).select_related("merchant__user", "merchant__agent", "payment_system")
    if ftd is not None:
        hit = qs.filter(ftd=bool(ftd)).first()
        if hit is not None:
            return hit
    # Prefer Standard-ish / any active
    return qs.order_by("ftd", "id").first()


def _trader_mdr_in(trader, payment_system) -> Decimal | None:
    from basics.models import TraderTeamRates

    if trader is None or getattr(trader, "team_id", None) is None or payment_system is None:
        return None
    row = TraderTeamRates.objects.filter(
        team_id=trader.team_id, payment_system=payment_system
    ).first()
    if row is None:
        return None
    return _d(row.mdr_in)


def _agent_pct(merchant) -> Decimal:
    agent = getattr(merchant, "agent", None) if merchant is not None else None
    if agent is None:
        return Decimal("0")
    return _d(agent.commission_percent)


def _teamlead_pct(trader) -> Decimal:
    team = getattr(trader, "team", None) if trader is not None else None
    if team is None:
        return Decimal("0")
    return _d(getattr(team, "teamlead_percentage", 0) or 0)


def quote_deal_margin(
    *,
    amount,
    payment_system,
    trader,
    merchant=None,
    solution=None,
    ftd=None,
) -> DealMarginQuote | None:
    """Оценка маржи до выдачи. None = не можем посчитать → не блокируем."""
    from merchant.tiered_mdr import effective_mdr_in
    from payments.dual_fx import quote_dual_fx

    if payment_system is None or trader is None:
        return None
    if solution is None:
        solution = _resolve_solution(merchant, payment_system, amount=amount, ftd=ftd)
    if solution is None:
        return None
    merchant = merchant or getattr(solution, "merchant", None)

    trader_mdr = _trader_mdr_in(trader, payment_system)
    if trader_mdr is None:
        return None

    amount = _d(amount)
    fx = quote_dual_fx(
        amount=amount,
        payment_system=payment_system,
        trader=trader,
        merchant=merchant,
    )
    merchant_mdr = _d(effective_mdr_in(solution, amount))
    merchant_usd = _money(fx.merchant_usd)
    psp_usd = _money(fx.psp_usd)
    if merchant_usd <= 0:
        return None

    merchant_fee = _money(merchant_usd * merchant_mdr / Decimal("100"))
    trader_fee = _money(psp_usd * trader_mdr / Decimal("100"))
    agent_pct = _agent_pct(merchant)
    agent_fee = _money(merchant_usd * agent_pct / Decimal("100"))
    tl_pct = _teamlead_pct(trader)
    teamlead_share = _money(merchant_usd * tl_pct / Decimal("100"))
    fx_spread = _money(psp_usd - merchant_usd)
    # Площадка платит trader_fee целиком (TL режется уже с трейдера) + agent_fee.
    platform_pnl = _money(merchant_fee + fx_spread - trader_fee - agent_fee)
    platform_pct = (platform_pnl * Decimal("100") / merchant_usd).quantize(
        PCTPLACES, rounding=ROUND_HALF_UP
    )
    min_pct = deal_margin_min_pct()
    return DealMarginQuote(
        amount=amount,
        merchant_usd=merchant_usd,
        psp_usd=psp_usd,
        merchant_rate=fx.merchant_rate,
        psp_rate=fx.psp_rate,
        merchant_mdr=merchant_mdr,
        trader_mdr=trader_mdr,
        merchant_fee=merchant_fee,
        trader_fee=trader_fee,
        agent_fee=agent_fee,
        teamlead_pct=tl_pct,
        teamlead_share=teamlead_share,
        fx_spread=fx_spread,
        platform_pnl=platform_pnl,
        platform_pct=platform_pct,
        min_pct=min_pct,
        ok=platform_pct >= min_pct,
    )


def trader_margin_ok_for_payin(
    *,
    amount,
    payment_system,
    trader,
    merchant=None,
    solution=None,
    ftd=None,
) -> tuple[bool, DealMarginQuote | None]:
    """True = можно выдавать. Фильтр выключен / нет данных → True."""
    if not deal_margin_filter_enabled():
        return True, None
    quote = quote_deal_margin(
        amount=amount,
        payment_system=payment_system,
        trader=trader,
        merchant=merchant,
        solution=solution,
        ftd=ftd,
    )
    if quote is None:
        return True, None
    if not quote.ok:
        try:
            uname = getattr(getattr(trader, "user", None), "username", None)
            mname = getattr(getattr(merchant, "user", None), "username", None)
            logger.info(
                "DEAL_MARGIN_SKIP merchant=%s trader=%s amount=%s pnl=%s pct=%s min=%s "
                "m_fee=%s t_fee=%s agent=%s tl_share=%s fx=%s",
                mname,
                uname,
                amount,
                quote.platform_pnl,
                quote.platform_pct,
                quote.min_pct,
                quote.merchant_fee,
                quote.trader_fee,
                quote.agent_fee,
                quote.teamlead_share,
                quote.fx_spread,
            )
        except Exception:
            pass
        return False, quote
    return True, quote


def margin_ok_for_group(group, *, amount, payment_system, merchant=None, ftd=None) -> tuple[bool, str | None]:
    trader = getattr(group, "trader", None)
    ok, quote = trader_margin_ok_for_payin(
        amount=amount,
        payment_system=payment_system,
        trader=trader,
        merchant=merchant,
        ftd=ftd,
    )
    if ok:
        return True, None
    return False, quote.as_skip_reason() if quote else "margin_low"
