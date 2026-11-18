"""Поиск двойных списаний/зачислений на одной заявке (баг ручного complete).

Исторически: трейдер жал «подтвердить» дважды → Charge/Deposit/Commission
два раза на один InOrder. Сейчас API: select_for_update + 409 если Completed.

Проверка леджера (read-only):

  docker compose exec -T app \\
    python manage.py shell < titanpay/basics/shell_diagnose_double_complete.py

Опционально:
  DAYS=7                 # окно по creation_date транзакций (0 = всё)
  SINCE=2026-11-01       # Europe/Moscow day (перекрывает DAYS)
  LIMIT=30               # сколько заявок-дублей печатать
  OUT=1                  # также OutOrder (Out-order completed)
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.db.models import Count, Q, Sum
from django.utils import timezone

from trade.models import InOrder, OutOrder, Transaction

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
DAYS = int((os.environ.get("DAYS") or "14").strip() or "14")
SINCE_RAW = (os.environ.get("SINCE") or "").strip()
LIMIT = int((os.environ.get("LIMIT") or "30").strip() or "30")
CHECK_OUT = (os.environ.get("OUT") or "").strip().lower() in {"1", "true", "yes"}

# Нормальный complete InOrder даёт ровно по одной «ноге» каждого типа
# (Charge frozen→agg, Deposit→merchant, Deposit Commission→trader).
IN_COMMENTS = (
    "In-order completed",
    "Commission",
)
OUT_COMMENTS = (
    "Out-order completed",
    "Out-order arbitrage",
)


def money(raw) -> Decimal:
    return Decimal(str(raw or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def money_str(raw) -> str:
    return f"{money(raw):,.2f}"


def window_start() -> datetime | None:
    if SINCE_RAW:
        try:
            return datetime.strptime(SINCE_RAW[:10], "%Y-%m-%d").replace(tzinfo=MSK)
        except ValueError:
            print(f"FAIL: bad SINCE={SINCE_RAW!r}")
            raise SystemExit(1)
    if DAYS <= 0:
        return None
    return timezone.now().astimezone(MSK) - timedelta(days=DAYS)


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


since = window_start()
print("=" * 72)
print("DOUBLE COMPLETE / LEDGER DUP DIAGNOSE  (read-only)")
print(f"  since={since.isoformat() if since else 'ALL'}  LIMIT={LIMIT}  OUT={int(CHECK_OUT)}")
print("=" * 72)
print(
    "API сейчас: POST /trade/order/in/<id>/complete/ → select_for_update + "
    "409 если уже Completed (trade/viewsets.py). Двойной клик не должен "
    "провести ledger дважды. Этот скрипт ищет ФАКТ дублей в Transaction."
)


def tx_qs(*, comments, linked_field: str):
    qs = Transaction.objects.filter(comment__in=comments)
    if linked_field == "in":
        qs = qs.filter(linked_in_order_id__isnull=False)
    else:
        qs = qs.filter(linked_out_order_id__isnull=False)
    if since is not None:
        qs = qs.filter(creation_date__gte=since)
    return qs


def find_group_dups(qs, order_field: str):
    """Группы (order, comment, type, value) с n>1."""
    return list(
        qs.values(order_field, "comment", "transaction_type__name", "value")
        .annotate(n=Count("id"), sum_v=Sum("value"))
        .filter(n__gte=2)
        .order_by("-n", order_field)
    )


def find_overcomplete_in(qs):
    """На одном InOrder: >1 Charge 'In-order completed' ИЛИ >1 Commission."""
    bad = []
    # Charge legs
    charge = (
        qs.filter(comment="In-order completed", transaction_type__name="Charge")
        .values("linked_in_order_id")
        .annotate(n=Count("id"), total=Sum("value"))
        .filter(n__gte=2)
    )
    for row in charge:
        bad.append(("charge_completed", row["linked_in_order_id"], row["n"], row["total"]))
    comm = (
        qs.filter(comment="Commission", transaction_type__name="Deposit")
        .values("linked_in_order_id")
        .annotate(n=Count("id"), total=Sum("value"))
        .filter(n__gte=2)
    )
    for row in comm:
        bad.append(("commission", row["linked_in_order_id"], row["n"], row["total"]))
    # Merchant deposit legs (same comment, Deposit, not Commission)
    merch = (
        qs.filter(comment="In-order completed", transaction_type__name="Deposit")
        .values("linked_in_order_id")
        .annotate(n=Count("id"), total=Sum("value"))
        .filter(n__gte=2)
    )
    for row in merch:
        bad.append(("merchant_deposit", row["linked_in_order_id"], row["n"], row["total"]))
    return bad


section("InOrder: дубли Charge / Merchant Deposit / Commission")
in_qs = tx_qs(comments=IN_COMMENTS, linked_field="in")
print(f"  txs in scope: {in_qs.count()}")

over = find_overcomplete_in(in_qs)
by_kind = defaultdict(list)
for kind, oid, n, total in over:
    by_kind[kind].append((oid, n, total))

for kind in ("charge_completed", "merchant_deposit", "commission"):
    rows = by_kind.get(kind, [])
    print(f"\n  {kind}: orders with n>=2 → {len(rows)}")
    shown = 0
    for oid, n, total in rows[:LIMIT]:
        shown += 1
        order = (
            InOrder.objects.select_related(
                "status",
                "solution__merchant__user",
                "payment_details__group__trader__user",
            )
            .filter(pk=oid)
            .first()
        )
        if order is None:
            print(f"    {oid} n={n} total={money_str(total)} (order missing)")
            continue
        trader = "-"
        try:
            trader = order.payment_details.group.trader.user.username
        except Exception:
            pass
        merch = "-"
        try:
            merch = order.solution.merchant.user.username
        except Exception:
            pass
        print(
            f"    {oid} n={n} sum={money_str(total)} status={order.status.name} "
            f"moid={order.merchant_order_id or '-'} trader={trader} merch={merch} "
            f"usd={money_str(order.usd_amount)} amt={money_str(order.amount)}"
        )
        txs = (
            Transaction.objects.filter(linked_in_order_id=oid)
            .filter(Q(comment__in=IN_COMMENTS) | Q(comment__icontains="completed"))
            .select_related("transaction_type")
            .order_by("creation_date", "id")
        )
        for tx in txs[:12]:
            print(
                f"      {tx.creation_date.astimezone(MSK).strftime('%m-%d %H:%M:%S')} "
                f"{tx.transaction_type.name:8} {money_str(tx.value):>10}  {tx.comment!r}  "
                f"from={tx.from_balance_id}→{tx.to_balance_id}"
            )
    if len(rows) > shown:
        print(f"    … +{len(rows) - shown} more")

# Exact group dups (same value too)
exact = find_group_dups(in_qs, "linked_in_order_id")
section(f"InOrder: точные дубли (order+comment+type+value) n>1 → {len(exact)}")
for row in exact[:LIMIT]:
    print(
        f"  {row['linked_in_order_id']}  {row['transaction_type__name']}  "
        f"{row['comment']!r}  value={money_str(row['value'])}  n={row['n']}"
    )

# Totals: how many Completed orders in window vs charge count
section("InOrder: sanity Completed vs Charge legs")
completed_q = InOrder.objects.filter(status__name="Completed")
if since is not None:
    completed_q = completed_q.filter(completion_date__gte=since)
n_completed = completed_q.count()
n_charge = (
    in_qs.filter(comment="In-order completed", transaction_type__name="Charge").count()
)
n_comm = in_qs.filter(comment="Commission", transaction_type__name="Deposit").count()
print(f"  Completed orders in window:     {n_completed}")
print(f"  Charge 'In-order completed':    {n_charge}")
print(f"  Deposit 'Commission':           {n_comm}")
print(
    f"  Δ charge−orders: {n_charge - n_completed}   "
    f"Δ commission−orders: {n_comm - n_completed}"
)
print("  (здорово ≈ 0; плюс = лишние проводки / минус = complete без Charge)")

if CHECK_OUT:
    section("OutOrder: дубли Out-order completed")
    out_qs = tx_qs(comments=OUT_COMMENTS, linked_field="out")
    out_dups = (
        out_qs.filter(comment="Out-order completed")
        .values("linked_out_order_id", "transaction_type__name", "value")
        .annotate(n=Count("id"))
        .filter(n__gte=2)
        .order_by("-n")
    )
    out_list = list(out_dups)
    print(f"  groups n>=2: {len(out_list)}")
    for row in out_list[:LIMIT]:
        oid = row["linked_out_order_id"]
        od = OutOrder.objects.select_related("status").filter(pk=oid).first()
        st = od.status.name if od else "?"
        print(
            f"  {oid} type={row['transaction_type__name']} "
            f"value={money_str(row['value'])} n={row['n']} status={st}"
        )

section("ВЕРДИКТ")
n_bad_orders = len({oid for _, oid, _, _ in over})
if n_bad_orders == 0:
    print("  Дублей Charge/Commission/Merchant Deposit на InOrder в окне НЕТ.")
    print("  Баг двойного ручного complete в текущих данных не проявляется.")
else:
    print(f"  ★ Найдено заявок с лишними ногами: {n_bad_orders}")
    print("  Разбери строки выше: две Charge 'In-order completed' = двойное списание.")
    print("  Код API сейчас лочит ордер; дубли могли остаться со старых версий / других entrypoints.")
print("DONE")
