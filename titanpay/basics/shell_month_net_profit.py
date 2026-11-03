"""
Чистая прибыль площадки за месяц (формула кассы).

NET = MDR_in + FX + MDR_out − trader_fee(in+out) − agent_fee − PlatformExpense

Оборот и доход только по Completed (InOrder/OutOrder.completion_date).
Расходы бота — PlatformExpense.created_at в том же окне (МСК).

Октябрь 2026:
  docker compose exec -T -e YEAR=2026 -e MONTH=10 app python manage.py shell \\
    < titanpay/basics/shell_month_net_profit.py

Из контейнера (/app):
  YEAR=2026 MONTH=10 python manage.py shell < basics/shell_month_net_profit.py

Опционально: MERCHANT=melbet  (только один мерч)
"""
from __future__ import annotations

import os
from calendar import monthrange
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from basics.models import PlatformExpense
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


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    last = monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=MSK)
    if month == 12:
        end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=MSK)
    else:
        end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=MSK)
    # sanity: last day exists
    assert start.day == 1 and end > start
    _ = last
    return start, end


def psp_effective_usd():
    return Case(
        When(psp_usd_amount__gt=0, then=F("psp_usd_amount")),
        default=F("usd_amount"),
        output_field=DEC,
    )


def run() -> None:
    start, end = month_bounds(YEAR, MONTH)
    print("=" * 72)
    print(f"NET PROFIT  {YEAR}-{MONTH:02d}  (Europe/Moscow)")
    print(f"  window: {start.isoformat()} → {end.isoformat()}")
    if MERCHANT:
        print(f"  merchant: {MERCHANT}")
    print("  formula: MDR_in + FX + MDR_out − PSP − agent − expenses")
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

    in_agg = in_qs.aggregate(
        merchant_fee=Coalesce(Sum("merchant_fee"), Value(ZERO, output_field=DEC)),
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
        merchant_fee=Coalesce(Sum("merchant_fee"), Value(ZERO, output_field=DEC)),
        trader_fee=Coalesce(Sum("trader_fee"), Value(ZERO, output_field=DEC)),
        turnover=Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)),
        fiat=Coalesce(Sum("amount"), Value(ZERO, output_field=DEC)),
        count=Count("id"),
    )

    exp_qs = PlatformExpense.objects.filter(created_at__gte=start, created_at__lt=end)
    expenses = exp_qs.aggregate(
        total=Coalesce(Sum("amount"), Value(ZERO, output_field=DEC)),
        count=Count("id"),
    )

    payin_mdr = money(in_agg["merchant_fee"])
    payin_fx = money(in_agg["fx_spread"])
    payin_trader = money(in_agg["trader_fee"])
    agent = money(in_agg["agent_fee"])
    payout_mdr = money(out_agg["merchant_fee"])
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

    print("\n=== ДОХОД ПЛОЩАДКИ ===")
    print(f"  + MDR pay-in:     {money_str(payin_mdr)}")
    print(f"  + FX-спред:       {money_str(payin_fx)}")
    print(f"  + MDR pay-out:    {money_str(payout_mdr)}")
    print(f"  − PSP (trader):   {money_str(payin_trader + payout_trader)}")
    print(f"  − агент:          {money_str(agent)}")
    print(f"  − расходы бота:   {money_str(expense_total)}  (n={expenses['count']})")
    print(f"  ================================")
    print(f"  NET (чистая):     {money_str(net)} USDT")
    if turnover > 0:
        print(f"  маржа от оборота: {100 * net / turnover:.2f}%")
        print(f"  оценка 2% оборота:{money_str(turnover * Decimal('0.02'))} USDT")

    # top merchants by NET contribution (pay-in only approximation)
    print("\n=== TOP мерчанты по NET pay-in (MDR+FX−PSP−agent) ===")
    rows = list(
        in_qs.values("solution__merchant__user__username").annotate(
            n=Count("id"),
            usd=Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)),
            mdr=Coalesce(Sum("merchant_fee"), Value(ZERO, output_field=DEC)),
            trader=Coalesce(Sum("trader_fee"), Value(ZERO, output_field=DEC)),
            agent_fee=Coalesce(Sum("agent_fee"), Value(ZERO, output_field=DEC)),
            fx=Coalesce(
                Sum(ExpressionWrapper(psp_effective_usd() - F("usd_amount"), output_field=DEC)),
                Value(ZERO, output_field=DEC),
            ),
        )
    )
    ranked = []
    for row in rows:
        contrib = money(row["mdr"]) + money(row["fx"]) - money(row["trader"]) - money(row["agent_fee"])
        ranked.append((contrib, row))
    ranked.sort(key=lambda x: -x[0])
    for contrib, row in ranked[:15]:
        name = row["solution__merchant__user__username"] or "?"
        print(
            f"  {name:<16} n={row['n']:5} USD={money_str(row['usd']):>12}  "
            f"net≈{money_str(contrib):>10}"
        )

    print("\n" + "=" * 72)
    print(f"DONE  net={money_str(net)} USDT for {YEAR}-{MONTH:02d}")
    print("=" * 72)


run()
