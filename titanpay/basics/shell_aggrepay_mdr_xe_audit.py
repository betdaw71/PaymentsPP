"""
Aggrepay C2CKZT IN: сверка комиссии с договором.

  до 09.09.2026 включительно — 7.30%
  с  10.09.2026             — 7.20%
  курс всегда XE+5% (usd_amount уже по нему, исторический = amount/usd_amount)

Просмотр 01–15 сентября (ничего не пишет):
  docker compose exec -T -e DATE_FROM=2026-09-01 -e DATE_TO=2026-09-15 \\
    app python manage.py shell < titanpay/basics/shell_aggrepay_mdr_xe_audit.py

Доначислить дельту (только дни после cutoff, где снимали 7.30 вместо 7.20):
  docker compose exec -T -e DATE_FROM=2026-09-01 -e DATE_TO=2026-09-15 -e APPLY=1 \\
    app python manage.py shell < titanpay/basics/shell_aggrepay_mdr_xe_audit.py

Ставки solutions наперёд 7.20%:
  docker compose exec -T -e APPLY_SOLUTIONS=1 \\
    app python manage.py shell < titanpay/basics/shell_aggrepay_mdr_xe_audit.py
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from basics.models import Balance
from merchant.models import MerchantSolution
from trade.models import InOrder, Transaction, TransactionType

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")
MERCHANT = (os.environ.get("MERCHANT") or "aggrepay").strip()
PS_NAME = (os.environ.get("PS_NAME") or "C2CKZT").strip()
DATE_FROM = (os.environ.get("DATE_FROM") or "2026-09-01").strip()
DATE_TO = (os.environ.get("DATE_TO") or "2026-09-15").strip()
CUTOFF = datetime.strptime(os.environ.get("CUTOFF") or "2026-09-09", "%Y-%m-%d").date()
MDR_BEFORE = Decimal(os.environ.get("MDR_BEFORE") or "7.30")
MDR_AFTER = Decimal(os.environ.get("MDR_AFTER") or "7.20")
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
APPLY_SOLUTIONS = (os.environ.get("APPLY_SOLUTIONS") or "").strip().lower() in {"1", "true", "yes"}
COMMENT = f"Aggrepay MDR correction to {MDR_AFTER}% after {CUTOFF.isoformat()} (XE+5)"


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def contract_mdr(when) -> Decimal:
    """Last day of 7.30% is CUTOFF (MSK calendar date of completion)."""
    if when is None:
        return MDR_AFTER
    if timezone.is_naive(when):
        when = timezone.make_aware(when, MSK)
    local = when.astimezone(MSK).date()
    return MDR_BEFORE if local <= CUTOFF else MDR_AFTER


def _day_bounds():
    start = timezone.make_aware(datetime.strptime(DATE_FROM, "%Y-%m-%d"), MSK)
    end_day = timezone.make_aware(datetime.strptime(DATE_TO, "%Y-%m-%d"), MSK)
    end = end_day.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def _qs(start, end):
    return (
        InOrder.objects.filter(
            solution__merchant__user__username=MERCHANT,
            solution__payment_system__name=PS_NAME,
            status__name="Completed",
            completion_date__gte=start,
            completion_date__lte=end,
        )
        .select_related(
            "solution",
            "solution__payment_system",
            "solution__merchant",
        )
        .order_by("completion_date")
    )


def _print_solutions() -> None:
    print(f"\n=== MerchantSolution {MERCHANT} {PS_NAME} ===")
    rows = MerchantSolution.objects.filter(
        merchant__user__username=MERCHANT,
        payment_system__name=PS_NAME,
    ).select_related("payment_system", "payment_system__currency", "traffic")
    for s in rows:
        cur = s.payment_system.currency.symbol if s.payment_system.currency_id else "?"
        mark = "" if s.mdr_in == MDR_AFTER else f"  <- not {MDR_AFTER}% (current contract)"
        print(
            f"  {s.payment_system.name:8} {cur:4} ftd={str(s.ftd):5} "
            f"traffic={s.traffic.name:10} mdr_in={s.mdr_in}% mdr_out={s.mdr_out}%{mark}"
        )


def _apply_solutions() -> int:
    qs = MerchantSolution.objects.filter(
        merchant__user__username=MERCHANT,
        payment_system__name=PS_NAME,
    ).exclude(mdr_in=MDR_AFTER)
    n = qs.count()
    if not APPLY_SOLUTIONS:
        print(f"\nsolutions to set mdr_in={MDR_AFTER}%: {n}  (APPLY_SOLUTIONS=1 to write)")
        return 0
    updated = qs.update(mdr_in=MDR_AFTER)
    print(f"\nAPPLY_SOLUTIONS: mdr_in={MDR_AFTER}% on {updated} C2CKZT solutions")
    return updated


def _apply_fees(rows: list[dict]) -> Decimal:
    payable = [r for r in rows if r["delta"] > 0]
    if not APPLY:
        print(
            f"\nDRY-RUN. To credit {len(payable)} deals / {money(sum((r['delta'] for r in payable), Decimal('0')))} USDT:\n"
            f"  docker compose exec -T -e DATE_FROM={DATE_FROM} -e DATE_TO={DATE_TO} -e APPLY=1 "
            f"app python manage.py shell < titanpay/basics/shell_aggrepay_mdr_xe_audit.py"
        )
        return Decimal("0")

    if not payable:
        print("APPLY: nothing to credit")
        return Decimal("0")

    merchant = payable[0]["order"].solution.merchant
    aggregator = Balance.objects.get(type=2)
    tx_type = TransactionType.objects.get(name="Deposit")
    credited = Decimal("0")
    n_ok = 0
    with transaction.atomic():
        for row in payable:
            order = InOrder.objects.select_for_update().get(pk=row["order"].pk)
            usd = money(order.usd_amount)
            mdr = contract_mdr(order.completion_date or order.creation_date)
            expected = money(usd * mdr / Decimal("100"))
            actual = money(order.merchant_fee)
            delta = money(actual - expected)
            if delta <= 0:
                continue
            order.merchant_fee = expected
            order.save(update_fields=["merchant_fee"])
            Transaction.create(
                _from=aggregator,
                _to=merchant.balance,
                value=delta,
                _transaction_type=tx_type,
                _linked_in_order=order,
                _comment=COMMENT,
            )
            credited += delta
            n_ok += 1
    print(f"\nAPPLY: credited {credited} USDT on {n_ok} deals")
    return credited


def run() -> None:
    start, end = _day_bounds()
    print(f"merchant={MERCHANT}  ps={PS_NAME}  XE+5%")
    print(f"MDR through {CUTOFF.isoformat()} inclusive: {MDR_BEFORE}%")
    print(f"MDR from {(date.fromordinal(CUTOFF.toordinal() + 1)).isoformat()}: {MDR_AFTER}%")
    print(f"period={start.isoformat()} .. {end.isoformat()}  APPLY={int(APPLY)} APPLY_SOLUTIONS={int(APPLY_SOLUTIONS)}")
    _print_solutions()

    qs = _qs(start, end)
    agg = qs.aggregate(n=Count("id"), fiat=Sum("amount"), usd=Sum("usd_amount"), fee=Sum("merchant_fee"))
    n = agg["n"] or 0
    fiat = money(agg["fiat"])
    usd = money(agg["usd"])
    fee = money(agg["fee"])
    implied_mdr = money(fee * 100 / usd) if usd else Decimal("0")
    implied_rate = (fiat / usd).quantize(Q4) if usd else None

    print(f"\n=== Completed {PS_NAME} ===")
    print(f"n={n}  fiat={fiat}  usd={usd}  fee={fee}")
    print(f"implied_mdr={implied_mdr}%  implied_avg_rate={implied_rate}")

    rows = []
    by_day = defaultdict(lambda: {"n": 0, "usd": Decimal("0"), "fee": Decimal("0"), "exp": Decimal("0"), "delta": Decimal("0")})
    for order in qs.iterator():
        o_usd = money(order.usd_amount)
        o_fiat = money(order.amount)
        o_fee = money(order.merchant_fee)
        mdr = contract_mdr(order.completion_date or order.creation_date)
        o_exp = money(o_usd * mdr / Decimal("100"))
        o_delta = money(o_fee - o_exp)
        o_rate = (o_fiat / o_usd).quantize(Q4) if o_usd else None
        o_pct = money(o_fee * 100 / o_usd) if o_usd else Decimal("0")
        when = order.completion_date or order.creation_date
        day = when.astimezone(MSK).date() if when else None
        rows.append({
            "order": order,
            "day": day,
            "mdr": mdr,
            "fiat": o_fiat,
            "usd": o_usd,
            "rate": o_rate,
            "mdr_sol": order.solution.mdr_in,
            "fee": o_fee,
            "expected": o_exp,
            "delta": o_delta,
            "pct": o_pct,
        })
        if day is not None:
            d = by_day[day]
            d["n"] += 1
            d["usd"] += o_usd
            d["fee"] += o_fee
            d["exp"] += o_exp
            d["delta"] += o_delta

    delta_sum = money(sum((r["delta"] for r in rows), Decimal("0")))
    expected_sum = money(sum((r["expected"] for r in rows), Decimal("0")))
    print(f"expected_fee (split MDR)={expected_sum}  overcharge={money(fee - expected_sum)} USDT")
    print(f"sum of per-deal deltas={delta_sum} USDT (это сумма к доначислению при APPLY=1)")
    print(f"deals with fee delta: {sum(1 for r in rows if r['delta'] != 0)} / {n}")

    print("\n=== by day (MSK completion) ===")
    print("day  n  usd  fee  contract%  expected  delta  implied%")
    for day in sorted(by_day):
        d = by_day[day]
        mdr = MDR_BEFORE if day <= CUTOFF else MDR_AFTER
        impl = money(d["fee"] * 100 / d["usd"]) if d["usd"] else Decimal("0")
        print(
            day, d["n"], money(d["usd"]), money(d["fee"]),
            f"{mdr}%", money(d["exp"]), money(d["delta"]), f"{impl}%",
        )

    if rows:
        rates = [r["rate"] for r in rows if r["rate"] is not None]
        print(f"\ndeal rate min={min(rates)} max={max(rates)}")
        print("sample (first 8):")
        print("id  day  fiat  usd  sol_mdr  contract%  fee  expected  delta")
        for r in rows[:8]:
            print(
                r["order"].id, r["day"], r["fiat"], r["usd"],
                f"{r['mdr_sol']}%", f"{r['mdr']}%", r["fee"], r["expected"], r["delta"],
            )

    _apply_solutions()
    if n:
        _apply_fees(rows)


run()
