"""
Влияние Melbet KGS/KZT Completed outs на «день» кассы (Europe/Moscow).

Показывает фиатный trader_fee, ошибочно учтённый как USDT, и правильный NET.

  DAY=2026-11-16 \\
  docker compose exec -T -e DAY app \\
    python manage.py shell < titanpay/basics/shell_diagnose_melbet_kgs_cash_impact.py
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.utils import timezone

from basics.cash_register import (
    melbet_fiat_merchant_fee_usd_expr,
    melbet_fiat_trader_fee_usd_expr,
    money,
    _period_pnl,
)
from trade.models import OutOrder

MSK = ZoneInfo("Europe/Moscow")
DAY = (os.environ.get("DAY") or "").strip()  # YYYY-MM-DD Moscow


def _day_bounds():
    if DAY:
        start = datetime.strptime(DAY, "%Y-%m-%d").replace(tzinfo=MSK)
    else:
        now = timezone.now().astimezone(MSK)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    end = start + timedelta(days=1)
    return start, end


def _fee_usd(fee, amount, usd) -> Decimal:
    fee, amount, usd = money(fee), money(amount), money(usd)
    if amount > 0 and usd > 0 and fee > usd:
        return money(fee * usd / amount)
    return fee


def main() -> None:
    start, end = _day_bounds()
    print(f"=== Melbet fiat OUT impact on cash day PnL ===")
    print(f"window MSK: {start.isoformat()} → {end.isoformat()}")

    outs = (
        OutOrder.objects.filter(
            status__name="Completed",
            completion_date__gte=start,
            completion_date__lt=end,
            solution__merchant__user__username__icontains="melbet",
        )
        .select_related(
            "solution__merchant__user",
            "solution__payment_system",
            "payment_details__group__trader__user",
        )
        .order_by("completion_date")
    )
    print(f"melbet completed outs: {outs.count()}")

    bad_raw = Decimal("0")
    fixed = Decimal("0")
    mdr_usd_total = Decimal("0")
    for o in outs:
        ps = o.solution.payment_system.name if o.solution_id and o.solution.payment_system_id else "?"
        tr = "-"
        if o.payment_details_id and o.payment_details.group_id:
            tr = o.payment_details.group.trader.user.username
        raw_tf = money(o.trader_fee)
        tf_usd = _fee_usd(o.trader_fee, o.amount, o.usd_amount)
        mf_usd = _fee_usd(o.merchant_fee, o.amount, o.usd_amount)
        # merchant always converted in cash via expr; show both
        if o.amount and o.usd_amount and money(o.merchant_fee) > 0:
            mf_usd = money(money(o.merchant_fee) * money(o.usd_amount) / money(o.amount))
        pnl_wrong = money(mf_usd - raw_tf)
        pnl_ok = money(mf_usd - tf_usd)
        bad_raw += raw_tf
        fixed += tf_usd
        mdr_usd_total += mf_usd
        flag = "FIAT_AS_USDT" if raw_tf > money(o.usd_amount) else "ok"
        print(
            f"  {o.merchant_order_id} {ps} amount={o.amount} usd={o.usd_amount} "
            f"m_fee={o.merchant_fee}(~{mf_usd}$) t_fee={o.trader_fee}→{tf_usd}$ "
            f"trader={tr} [{flag}]"
        )
        print(f"    day PnL contrib wrong={pnl_wrong}  fixed={pnl_ok}")

    print(f"\nsum trader_fee raw (as old cash): {money(bad_raw)}")
    print(f"sum trader_fee USDT (fixed):     {money(fixed)}")
    print(f"sum merchant_fee USDT:           {money(mdr_usd_total)}")
    print(f"delta over-subtracted from day:  {money(bad_raw - fixed)}")

    day = _period_pnl(start, end)
    print(f"\n=== full day PnL (with fix in code) ===")
    for k in (
        "orders_in",
        "orders_out",
        "payin_mdr",
        "payin_fx",
        "payout_mdr",
        "trader_fee",
        "agent_fee",
        "expenses",
        "net",
    ):
        print(f"  {k}={day[k]}")

    # Compare raw Sum(trader_fee) vs converted
    raw_sum = outs.aggregate(s=Sum("trader_fee"))["s"] or 0
    conv = outs.aggregate(s=Sum(melbet_fiat_trader_fee_usd_expr()))["s"] or 0
    mdr = outs.aggregate(s=Sum(melbet_fiat_merchant_fee_usd_expr()))["s"] or 0
    print(f"\nmelbet-outs only: raw_trader_fee={money(raw_sum)} conv={money(conv)} mdr_usd={money(mdr)}")
    print(f"  → тест w5547812021 с fee 125 KGS давал ~−{money(Decimal(str(raw_sum))-Decimal(str(conv)))} к дню")


main()
