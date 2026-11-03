"""
Чистая прибыль площадки за месяц (формула кассы), MDR Melbet в USDT.

У Melbet (KZT/KGS ledger) merchant_fee хранится в фиате — конвертируем:
  fee_usd = merchant_fee * usd_amount / amount
Иначе merchant_fee уже USDT.

NET = MDR_in_usd + FX + MDR_out_usd − trader_fee − agent_fee − PlatformExpense

Октябрь 2026:
  docker compose exec -T -e YEAR=2026 -e MONTH=10 app python manage.py shell \\
    < titanpay/basics/shell_month_net_profit.py

Из контейнера (/app):
  YEAR=2026 MONTH=10 python manage.py shell < basics/shell_month_net_profit.py

Опционально: MERCHANT=melbet
"""
from __future__ import annotations

import os
from calendar import monthrange
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, Sum, Value, When
from django.db.models.functions import Coalesce

from basics.models import PlatformExpense
from merchant.kzt_settlement import (
    melbet_kgs_ps_names,
    melbet_kzt_ps_names,
    melbet_kzt_usernames,
    uses_melbet_fiat_settlement,
)
from trade.models import InOrder, OutOrder

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
ZERO = Decimal("0.00")
DEC = DecimalField(max_digits=32, decimal_places=2)

YEAR = int(os.environ.get("YEAR") or "2026")
MONTH = int(os.environ.get("MONTH") or "10")
MERCHANT = (os.environ.get("MERCHANT") or "").strip()


def money(raw) -> Decimal:
    return Decimal(str(raw or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def money_str(raw) -> str:
    return f"{money(raw):,.2f}"


def merchant_fee_to_usd(merchant_fee, amount, usd_amount, *, fiat_settlement: bool) -> Decimal:
    fee = money(merchant_fee)
    if not fiat_settlement:
        return fee
    amt = money(amount)
    usd = money(usd_amount)
    if amt <= 0 or usd <= 0:
        return ZERO
    return money(fee * usd / amt)


def psp_effective_usd():
    return Case(
        When(psp_usd_amount__gt=0, then=F("psp_usd_amount")),
        default=F("usd_amount"),
        output_field=DEC,
    )


def melbet_fiat_merchant_fee_usd_expr():
    """Self-contained: works even if container cash_register is stale."""
    try:
        from basics.cash_register import melbet_fiat_merchant_fee_usd_expr as _shared

        return _shared()
    except ImportError:
        pass
    melbet_names = sorted(melbet_kzt_usernames())
    fiat_ps = sorted({*(n.upper() for n in melbet_kzt_ps_names()), *(n.upper() for n in melbet_kgs_ps_names())})
    fiat_fee_usd = ExpressionWrapper(
        F("merchant_fee") * F("usd_amount") / F("amount"),
        output_field=DEC,
    )
    return Case(
        When(
            solution__merchant__user__username__in=melbet_names,
            solution__payment_system__name__in=fiat_ps,
            amount__gt=0,
            usd_amount__gt=0,
            then=fiat_fee_usd,
        ),
        default=F("merchant_fee"),
        output_field=DEC,
    )


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    _ = monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=MSK)
    if month == 12:
        end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=MSK)
    else:
        end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=MSK)
    return start, end


def run() -> None:
    start, end = month_bounds(YEAR, MONTH)
    print("=" * 72)
    print(f"NET PROFIT  {YEAR}-{MONTH:02d}  (Europe/Moscow)")
    print(f"  window: {start.isoformat()} → {end.isoformat()}")
    if MERCHANT:
        print(f"  merchant: {MERCHANT}")
    print("  formula: MDR_usd + FX + MDR_out_usd − PSP − agent − expenses")
    print("  note: Melbet merchant_fee (KZT/KGS) → USDT via fee*usd/amount")
    print("=" * 72)

    in_qs = InOrder.objects.filter(
        status__name="Completed",
        completion_date__gte=start,
        completion_date__lt=end,
    )
    out_qs = OutOrder.objects.filter(
        status__name="Completed",
        completion_date__gte=start,
        completion_date__lt=end,
    )
    if MERCHANT:
        in_qs = in_qs.filter(solution__merchant__user__username=MERCHANT)
        out_qs = out_qs.filter(solution__merchant__user__username=MERCHANT)

    mdr_usd = melbet_fiat_merchant_fee_usd_expr()
    in_agg = in_qs.aggregate(
        merchant_fee_usd=Coalesce(Sum(mdr_usd), Value(ZERO, output_field=DEC)),
        merchant_fee_raw=Coalesce(Sum("merchant_fee"), Value(ZERO, output_field=DEC)),
        trader_fee=Coalesce(Sum("trader_fee"), Value(ZERO, output_field=DEC)),
        agent_fee=Coalesce(Sum("agent_fee"), Value(ZERO, output_field=DEC)),
        fx_spread=Coalesce(
            Sum(ExpressionWrapper(psp_effective_usd() - F("usd_amount"), output_field=DEC)),
            Value(ZERO, output_field=DEC),
        ),
        turnover=Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)),
        fiat=Coalesce(Sum("amount"), Value(ZERO, output_field=DEC)),
        count=Count("id"),
    )
    out_agg = out_qs.aggregate(
        merchant_fee_usd=Coalesce(Sum(mdr_usd), Value(ZERO, output_field=DEC)),
        merchant_fee_raw=Coalesce(Sum("merchant_fee"), Value(ZERO, output_field=DEC)),
        trader_fee=Coalesce(Sum("trader_fee"), Value(ZERO, output_field=DEC)),
        turnover=Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)),
        fiat=Coalesce(Sum("amount"), Value(ZERO, output_field=DEC)),
        count=Count("id"),
    )

    expenses = PlatformExpense.objects.filter(created_at__gte=start, created_at__lt=end).aggregate(
        total=Coalesce(Sum("amount"), Value(ZERO, output_field=DEC)),
        count=Count("id"),
    )

    payin_mdr = money(in_agg["merchant_fee_usd"])
    payin_fx = money(in_agg["fx_spread"])
    payin_trader = money(in_agg["trader_fee"])
    agent = money(in_agg["agent_fee"])
    payout_mdr = money(out_agg["merchant_fee_usd"])
    payout_trader = money(out_agg["trader_fee"])
    expense_total = money(expenses["total"])
    turnover = money(in_agg["turnover"]) + money(out_agg["turnover"])

    net = money(
        payin_mdr
        + payin_fx
        + payout_mdr
        - payin_trader
        - payout_trader
        - agent
        - expense_total
    )

    print("\n=== ОБОРОТ (Completed) ===")
    print(f"  IN : n={in_agg['count']}  USD={money_str(in_agg['turnover'])}  fiat={money_str(in_agg['fiat'])}")
    print(f"  OUT: n={out_agg['count']}  USD={money_str(out_agg['turnover'])}  fiat={money_str(out_agg['fiat'])}")
    print(f"  TOTAL USD: {money_str(turnover)}")

    print("\n=== ДОХОД ПЛОЩАДКИ (USDT) ===")
    print(f"  + MDR pay-in USD: {money_str(payin_mdr)}  (raw fee sum={money_str(in_agg['merchant_fee_raw'])})")
    print(f"  + FX-спред:       {money_str(payin_fx)}")
    print(f"  + MDR pay-out USD:{money_str(payout_mdr)}  (raw fee sum={money_str(out_agg['merchant_fee_raw'])})")
    print(f"  − PSP (trader):   {money_str(payin_trader + payout_trader)}")
    print(f"  − агент:          {money_str(agent)}")
    print(f"  − расходы бота:   {money_str(expense_total)}  (n={expenses['count']})")
    print(f"  ================================")
    print(f"  NET (чистая):     {money_str(net)} USDT")
    if turnover > 0:
        print(f"  маржа от оборота: {100 * net / turnover:.2f}%")
        print(f"  оценка 2% оборота:{money_str(turnover * Decimal('0.02'))} USDT")

    print("\n=== TOP мерчанты по NET pay-in (MDR_usd+FX−PSP−agent) ===")
    by_m: dict[str, dict] = {}
    qs = in_qs.select_related(
        "solution__merchant__user",
        "solution__payment_system",
    )
    for order in qs.iterator(chunk_size=500):
        merchant = order.solution.merchant if order.solution_id else None
        username = merchant.user.username if merchant and merchant.user_id else "?"
        fiat = uses_melbet_fiat_settlement(
            merchant,
            order.solution.payment_system if order.solution_id else None,
        )
        mdr = merchant_fee_to_usd(
            order.merchant_fee,
            order.amount,
            order.usd_amount,
            fiat_settlement=fiat,
        )
        psp_usd = order.psp_usd_amount if order.psp_usd_amount and order.psp_usd_amount > 0 else order.usd_amount
        fx = money(psp_usd) - money(order.usd_amount)
        cell = by_m.setdefault(username, {"n": 0, "usd": ZERO, "net": ZERO})
        cell["n"] += 1
        cell["usd"] += money(order.usd_amount)
        cell["net"] += money(mdr + fx - money(order.trader_fee) - money(order.agent_fee))

    ranked = sorted(by_m.items(), key=lambda kv: -kv[1]["net"])
    for name, cell in ranked[:15]:
        print(
            f"  {name:<16} n={cell['n']:5} USD={money_str(cell['usd']):>12}  "
            f"net≈{money_str(cell['net']):>10}"
        )

    print("\n" + "=" * 72)
    print(f"DONE  net={money_str(net)} USDT for {YEAR}-{MONTH:02d}")
    print("=" * 72)


run()
