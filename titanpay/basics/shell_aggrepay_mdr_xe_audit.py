"""
Aggrepay: сверка IN с договором 7.2% @ XE+5% (по умолчанию 12.09.2026 MSK).

Курс на заявке не хранится. usd_amount уже посчитан как fiat / PS-курс на момент
создания, а KZT-курс платформы = XE mid-market × 1.05. Исторический курс сделки
= amount / usd_amount. Это и есть XE+5% на секунду создания (с округлением USDT
до 0.01). Текущий PS-курс для сверки 12.09 не использовать.

Комиссия в БД: merchant_fee = solution.mdr_in% × usd_amount.
На 12.09 у aggrepay в solutions стояло 7.30% при договоре 7.20%.

Просмотр (ничего не пишет):
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_aggrepay_mdr_xe_audit.py

Другой день:
  docker compose exec -T -e DATE_FROM=2026-09-12 -e DATE_TO=2026-09-12 \\
    app python manage.py shell < titanpay/basics/shell_aggrepay_mdr_xe_audit.py

Пересчёт комиссий 7.30→7.20 и доначисление дельты на USDT-баланс мерчанта:
  docker compose exec -T -e APPLY=1 app python manage.py shell < titanpay/basics/shell_aggrepay_mdr_xe_audit.py

Ставки solutions C2CKZT наперёд 7.20% (отдельно от пересчёта заявок):
  docker compose exec -T -e APPLY_SOLUTIONS=1 app python manage.py shell < titanpay/basics/shell_aggrepay_mdr_xe_audit.py
"""
from __future__ import annotations

import os
from datetime import datetime
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
CONTRACT_MDR = Decimal(os.environ.get("CONTRACT_MDR") or "7.20")
MERCHANT = (os.environ.get("MERCHANT") or "aggrepay").strip()
PS_NAME = (os.environ.get("PS_NAME") or "C2CKZT").strip()
DATE_FROM = (os.environ.get("DATE_FROM") or "2026-09-12").strip()
DATE_TO = (os.environ.get("DATE_TO") or DATE_FROM).strip()
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
APPLY_SOLUTIONS = (os.environ.get("APPLY_SOLUTIONS") or "").strip().lower() in {"1", "true", "yes"}
COMMENT = "Aggrepay MDR correction 7.30% -> 7.20% per contract XE+5"


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


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
            "payment_details__group__trader__user",
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
        mark = ""
        if s.mdr_in != CONTRACT_MDR:
            mark = f"  <- not {CONTRACT_MDR}%"
        print(
            f"  {s.payment_system.name:8} {cur:4} ftd={str(s.ftd):5} "
            f"traffic={s.traffic.name:10} mdr_in={s.mdr_in}% mdr_out={s.mdr_out}%{mark}"
        )


def _apply_solutions() -> int:
    qs = MerchantSolution.objects.filter(
        merchant__user__username=MERCHANT,
        payment_system__name=PS_NAME,
    ).exclude(mdr_in=CONTRACT_MDR)
    n = qs.count()
    if not APPLY_SOLUTIONS:
        print(f"\nsolutions to set mdr_in={CONTRACT_MDR}%: {n}  (APPLY_SOLUTIONS=1 to write)")
        return 0
    updated = qs.update(mdr_in=CONTRACT_MDR)
    print(f"\nAPPLY_SOLUTIONS: mdr_in={CONTRACT_MDR}% on {updated} C2CKZT solutions")
    return updated


def _apply_fees(rows: list[dict]) -> Decimal:
    payable = [r for r in rows if r["delta"] > 0]
    if not APPLY:
        print(f"\nDRY-RUN. To credit {len(payable)} deals: docker compose exec -T -e APPLY=1 app python manage.py shell < titanpay/basics/shell_aggrepay_mdr_xe_audit.py")
        return Decimal("0")

    merchant = payable[0]["order"].solution.merchant if payable else None
    if merchant is None:
        print("APPLY: nothing to credit")
        return Decimal("0")

    aggregator = Balance.objects.get(type=2)
    tx_type = TransactionType.objects.get(name="Deposit")
    credited = Decimal("0")
    with transaction.atomic():
        for row in payable:
            order = InOrder.objects.select_for_update().get(pk=row["order"].pk)
            usd = money(order.usd_amount)
            expected = money(usd * CONTRACT_MDR / Decimal("100"))
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
    print(f"\nAPPLY: credited {credited} USDT on {len(payable)} deals, merchant_fee set to {CONTRACT_MDR}%")
    return credited


def run() -> None:
    start, end = _day_bounds()
    print(f"merchant={MERCHANT}  ps={PS_NAME}  contract MDR={CONTRACT_MDR}% @ XE+5%")
    print(f"period={start.isoformat()} .. {end.isoformat()}  APPLY={int(APPLY)} APPLY_SOLUTIONS={int(APPLY_SOLUTIONS)}")
    _print_solutions()

    qs = _qs(start, end)
    agg = qs.aggregate(n=Count("id"), fiat=Sum("amount"), usd=Sum("usd_amount"), fee=Sum("merchant_fee"))
    n = agg["n"] or 0
    fiat = money(agg["fiat"])
    usd = money(agg["usd"])
    fee = money(agg["fee"])
    expected_fee = money(usd * CONTRACT_MDR / Decimal("100")) if usd else Decimal("0")
    overcharge = money(fee - expected_fee)
    implied_mdr = money(fee * 100 / usd) if usd else Decimal("0")
    implied_rate = (fiat / usd).quantize(Q4) if usd else None

    print(f"\n=== Completed {PS_NAME} ===")
    print(f"n={n}  fiat={fiat}  usd={usd}  fee={fee}")
    print(f"implied_mdr={implied_mdr}%  (contract {CONTRACT_MDR}%)")
    print(f"implied_avg_rate={implied_rate}  (= amount/usd_amount, XE+5 at create)")
    print(f"expected_fee_at_{CONTRACT_MDR}%={expected_fee}  overcharge={overcharge} USDT")

    rows = []
    for order in qs.iterator():
        o_usd = money(order.usd_amount)
        o_fiat = money(order.amount)
        o_fee = money(order.merchant_fee)
        o_exp = money(o_usd * CONTRACT_MDR / Decimal("100"))
        o_delta = money(o_fee - o_exp)
        o_rate = (o_fiat / o_usd).quantize(Q4) if o_usd else None
        o_pct = money(o_fee * 100 / o_usd) if o_usd else Decimal("0")
        rows.append({
            "order": order,
            "fiat": o_fiat,
            "usd": o_usd,
            "rate": o_rate,
            "mdr_sol": order.solution.mdr_in,
            "fee": o_fee,
            "expected": o_exp,
            "delta": o_delta,
            "pct": o_pct,
        })

    delta_sum = money(sum((r["delta"] for r in rows), Decimal("0")))
    print(f"sum of per-deal deltas={delta_sum} USDT (это сумма к доначислению при APPLY=1)")
    nonzero = [r for r in rows if r["delta"] != 0]
    print(f"deals with fee delta vs {CONTRACT_MDR}%: {len(nonzero)} / {n}")
    if rows:
        rates = [r["rate"] for r in rows if r["rate"] is not None]
        print(f"deal rate min={min(rates)} max={max(rates)}")
        print("\nsample (first 8):")
        print("id  fiat  usd  rate  sol_mdr  fee  expected  delta  fee%")
        for r in rows[:8]:
            print(
                r["order"].id, r["fiat"], r["usd"], r["rate"],
                f"{r['mdr_sol']}%", r["fee"], r["expected"], r["delta"], f"{r['pct']}%",
            )

    _apply_solutions()
    if n:
        _apply_fees(rows)


run()
