"""Забрать с resdfe/resdfe1 курсовую разницу xe+4, которую не списали при complete.

Новые заявки после деплоя freeze/complete уже идут по psp_usd.
Этот скрипт — только уже Completed: Charge был на merchant usd.

Dry-run:
  docker compose exec -T app \\
    python manage.py shell < titanpay/basics/shell_clawback_resdfe_xe4.py

Применить:
  docker compose exec -T -e APPLY=1 app \\
    python manage.py shell < titanpay/basics/shell_clawback_resdfe_xe4.py

С баланса команды уходит (target_psp − charge) и возвращается разница комиссии 4%.
Идемпотентно: повтор не проведёт заявку с комментарием «FX xe+4 clawback».
"""
from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction as db_transaction
from django.db.models import Sum

from basics.models import Trader, TraderTeamRates
from payments.dual_fx import merchant_fx_markup
from trade.models import Balance, InOrder, Transaction, TransactionType

Q2 = Decimal("0.01")
Q3 = Decimal("0.001")
ZERO = Decimal("0.00")
TRADERS = [
    x.strip()
    for x in (os.environ.get("TRADERS") or "resdfe,resdfe1").split(",")
    if x.strip()
]
TARGET_XE = Decimal((os.environ.get("TARGET_XE") or "1.04").strip() or "1.04")
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
COMMENT = "FX xe+4 clawback"


def money(raw) -> Decimal:
    return Decimal(str(raw or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def ms(raw) -> str:
    return f"{money(raw):,.2f}"


def expected_psp(order) -> tuple[Decimal, Decimal]:
    """→ (psp_usd, psp_rate) при TARGET_XE от курса мерчанта на ордере."""
    amount = Decimal(str(order.amount or 0))
    usd = Decimal(str(order.usd_amount or 0))
    if amount <= 0 or usd <= 0:
        return money(usd), Decimal("0")
    ps = order.solution.payment_system if order.solution_id else None
    merch = order.solution.merchant if order.solution_id else None
    mm = merchant_fx_markup(ps, merchant=merch)
    mr = Decimal(str(getattr(order, "merchant_rate", 0) or 0))
    if mr <= 0:
        mr = (amount / usd).quantize(Q3, rounding=ROUND_HALF_UP)
    if mm <= 0 or TARGET_XE <= 0 or mr <= 0:
        return money(usd), mr
    psp_rate = (mr * TARGET_XE / mm).quantize(Q3, rounding=ROUND_HALF_UP)
    if psp_rate <= 0:
        return money(usd), mr
    return money(amount / psp_rate), psp_rate


def mdr_in(order, trader) -> Decimal:
    ps = order.solution.payment_system if order.solution_id else None
    if trader.team_id and ps is not None:
        row = (
            TraderTeamRates.objects.filter(team_id=trader.team_id, payment_system=ps)
            .only("mdr_in")
            .first()
        )
        if row is not None and row.mdr_in is not None:
            return Decimal(str(row.mdr_in))
    if trader.team_id and trader.team.rate_in is not None:
        return Decimal(str(trader.team.rate_in))
    return Decimal("4")


print("=" * 72)
print(f"CLAWBACK xe+{TARGET_XE}  APPLY={int(APPLY)}  traders={','.join(TRADERS)}")
print("=" * 72)

agg = Balance.objects.get(type=2)
tx_charge = TransactionType.objects.get(name="Charge")
tx_deposit = TransactionType.objects.get(name="Deposit")

grand_fx = ZERO
grand_fee = ZERO
grand_net = ZERO
grand_n = 0

for username in TRADERS:
    trader = (
        Trader.objects.select_related("user", "team", "balance_usdt")
        .filter(user__username=username)
        .first()
    )
    print()
    print(f"--- {username} ---")
    if trader is None or trader.balance_usdt_id is None:
        print("  NOT FOUND")
        continue
    before = money(trader.balance_usdt.amount)
    print(f"  available now={ms(before)}")

    orders = list(
        InOrder.objects.filter(
            status__name="Completed",
            payment_details__group__trader=trader,
        ).select_related("solution__payment_system", "solution__merchant")
    )
    ids = [o.id for o in orders]
    charged = {}
    comm = {}
    if ids:
        rows = (
            Transaction.objects.filter(linked_in_order_id__in=ids)
            .filter(comment__in=["In-order completed", "Commission"])
            .values("linked_in_order_id", "comment", "transaction_type__name")
            .annotate(s=Sum("value"))
        )
        for row in rows:
            if row["comment"] == "In-order completed" and row["transaction_type__name"] == "Charge":
                charged[row["linked_in_order_id"]] = money(row["s"])
            elif row["comment"] == "Commission" and row["transaction_type__name"] == "Deposit":
                comm[row["linked_in_order_id"]] = money(row["s"])
    done_ids = set(
        Transaction.objects.filter(
            linked_in_order_id__in=ids,
            comment__startswith=COMMENT,
        ).values_list("linked_in_order_id", flat=True)
    ) if ids else set()

    fx_sum = ZERO
    fee_sum = ZERO
    net_sum = ZERO
    n = 0
    skipped = 0
    for order in orders:
        if order.id in done_ids:
            skipped += 1
            continue
        target, psp_rate = expected_psp(order)
        got = charged.get(order.id, ZERO)
        fee_paid = comm.get(order.id, ZERO)
        if got <= 0 or target <= 0:
            continue
        fx_gap = money(target - got)
        new_fee = money(mdr_in(order, trader) * target / Decimal(100))
        fee_gap = money(new_fee - fee_paid)
        net = money(fx_gap - fee_gap)
        if fx_gap < Q2 and abs(fee_gap) < Q2:
            continue
        n += 1
        fx_sum += fx_gap
        fee_sum += fee_gap
        net_sum += net
        if APPLY:
            with db_transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=order.id)
                if Transaction.objects.filter(
                    linked_in_order=locked, comment__startswith=COMMENT
                ).exists():
                    continue
                t = locked.payment_details.group.trader
                if fx_gap >= Q2:
                    Transaction.create(
                        _from=t.balance_usdt,
                        _to=agg,
                        value=fx_gap,
                        _transaction_type=tx_charge,
                        _linked_in_order=locked,
                        _comment=f"{COMMENT} charge",
                    )
                if fee_gap >= Q2:
                    Transaction.create(
                        _from=agg,
                        _to=t.balance_usdt,
                        value=fee_gap,
                        _transaction_type=tx_deposit,
                        _linked_in_order=locked,
                        _comment=f"{COMMENT} fee",
                    )
                elif fee_gap <= -Q2:
                    Transaction.create(
                        _from=t.balance_usdt,
                        _to=agg,
                        value=-fee_gap,
                        _transaction_type=tx_charge,
                        _linked_in_order=locked,
                        _comment=f"{COMMENT} fee",
                    )
                locked.psp_usd_amount = target
                locked.psp_rate = psp_rate
                locked.trader_fee = new_fee
                locked.save(update_fields=["psp_usd_amount", "psp_rate", "trader_fee"])

    print(f"  orders to touch={n}  already={skipped}")
    print(f"  FX charge:     {ms(fx_sum)}")
    print(f"  fee adjust:    {ms(fee_sum)}  (плюс = доплатить команде)")
    print(f"  ★ net с ЛК:    {ms(net_sum)}")
    if APPLY:
        trader.balance_usdt.refresh_from_db()
        print(f"  available after={ms(trader.balance_usdt.amount)}  (was {ms(before)})")
    grand_fx += fx_sum
    grand_fee += fee_sum
    grand_net += net_sum
    grand_n += n

print()
print("=" * 72)
print(f"ИТОГО orders={grand_n}  FX={ms(grand_fx)}  fee_adj={ms(grand_fee)}  net с ЛК={ms(grand_net)}")
if not APPLY:
    print("DRY-RUN. Применить: APPLY=1")
else:
    print("APPLIED")
print("DONE")
