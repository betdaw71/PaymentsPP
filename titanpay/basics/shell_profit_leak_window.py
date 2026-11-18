"""Куда делась маржа за последние дни, помимо бага xe+4 на команде.

Главная гипотеза: Melbet prepaid заливается по xe+4.5
(shell_melbet_kzt_prepaid_debit.py), а заявка списывает тенге и считает
USD по xe+5. На одном и том же объёме KZT реальный USDT дороже,
чем usd_amount в ордере. В NET этой разницы нет — касса в блокноте
отстаёт от «дохода».

  docker compose exec -T -e DAYS=4 app \\
    python manage.py shell < titanpay/basics/shell_profit_leak_window.py

  BUY_MARKUP=1.045   # курс залива
  DAYS=4
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

from basics.cash_register import MSK, _period_pnl, money
from payments.dual_fx import merchant_fx_markup
from payments.psp_payin import is_psp_trader
from trade.models import InOrder, Transaction

Q2 = Decimal("0.01")
Q3 = Decimal("0.001")
ZERO = Decimal("0.00")
DAYS = int((os.environ.get("DAYS") or "4").strip() or "4")
BUY_MARKUP = Decimal((os.environ.get("BUY_MARKUP") or "1.045").strip() or "1.045")


def ms(raw) -> str:
    return f"{money(raw):,.2f}"


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


now = timezone.now().astimezone(MSK)
since = now - timedelta(days=DAYS)
print("=" * 72)
print(f"PROFIT LEAK WINDOW  {since.isoformat()} → {now.isoformat()}  (Europe/Moscow)")
print(f"  buy markup xe+{BUY_MARKUP}   order markup берётся с заявки (у Melbet обычно 1.05)")
print("=" * 72)

pnl = _period_pnl(since, now)
print(f"  NET системы за окно: {pnl['net']}   in={pnl['orders_in']}  turnover={pnl['turnover_in']}")

orders = (
    InOrder.objects.filter(status__name="Completed", completion_date__gte=since, completion_date__lt=now)
    .select_related(
        "solution__merchant__user",
        "solution__payment_system",
        "payment_details__group__trader__user",
    )
)

ids = []
rows = []
for order in orders.iterator(chunk_size=400):
    ids.append(order.id)
    rows.append(order)

charge = defaultdict(lambda: ZERO)
claw = defaultdict(lambda: ZERO)
if ids:
    for chunk_start in range(0, len(ids), 800):
        part = ids[chunk_start:chunk_start + 800]
        agg = (
            Transaction.objects.filter(linked_in_order_id__in=part)
            .filter(comment__in=["In-order completed", "FX xe+4 clawback charge"])
            .values("linked_in_order_id", "comment", "transaction_type__name")
            .annotate(s=Sum("value"))
        )
        for row in agg:
            if row["comment"] == "In-order completed" and row["transaction_type__name"] == "Charge":
                charge[row["linked_in_order_id"]] += money(row["s"])
            elif row["comment"] == "FX xe+4 clawback charge":
                claw[row["linked_in_order_id"]] += money(row["s"])

melbet_booked = ZERO
melbet_real = ZERO
melbet_gap = ZERO
melbet_n = 0
melbet_credit_kzt = ZERO
by_trader_fx = defaultdict(lambda: ZERO)
by_trader_n = defaultdict(int)
neg_pnl = ZERO
neg_n = 0
human_fx_left = ZERO

for order in rows:
    usd = money(order.usd_amount)
    amount = Decimal(str(order.amount or 0))
    fee = Decimal(str(order.merchant_fee or 0))
    merch = ""
    try:
        merch = (order.solution.merchant.user.username or "").lower()
    except Exception:
        merch = ""
    ps = order.solution.payment_system if order.solution_id else None
    mm = merchant_fx_markup(ps, merchant=merch)
    mr = Decimal(str(getattr(order, "merchant_rate", 0) or 0))
    if mr <= 0 and usd > 0 and amount > 0:
        mr = (amount / usd).quantize(Q3, rounding=ROUND_HALF_UP)

    # Melbet: prepaid падает на (amount − fee) KZT. Залив был по xe+4.5, ордер по xe+5.
    if merch == "melbet" and amount > 0 and mr > 0 and mm > 0 and fee > usd:
        credit_kzt = money(amount - fee)
        buy_rate = (mr / mm * BUY_MARKUP).quantize(Q3, rounding=ROUND_HALF_UP)
        if buy_rate > 0:
            real_usd = money(credit_kzt / buy_rate)
            booked_usd = money(credit_kzt / mr)
            gap = money(real_usd - booked_usd)
            melbet_n += 1
            melbet_credit_kzt += credit_kzt
            melbet_booked += booked_usd
            melbet_real += real_usd
            melbet_gap += gap

    trader = None
    tname = ""
    try:
        trader = order.payment_details.group.trader
        tname = trader.user.username
    except Exception:
        trader = None
    psp_usd = money(order.psp_usd_amount) or usd
    charged = charge[order.id] + claw[order.id]
    if charged <= 0:
        charged = usd
    fx_left = money(psp_usd - charged)
    if fx_left >= Q2 and trader is not None and not is_psp_trader(trader):
        human_fx_left += fx_left
        by_trader_fx[tname] += fx_left
        by_trader_n[tname] += 1

    mfee_usd = money(fee * usd / amount) if amount > 0 and fee > usd else money(fee)
    deal = money(mfee_usd + (psp_usd - usd) - money(order.trader_fee) - money(order.agent_fee))
    if deal < 0:
        neg_n += 1
        neg_pnl += deal

section("H1  Melbet залив xe+4.5 против ордера xe+5")
print(f"  заявок Melbet с фиатной комиссией: {melbet_n}")
print(f"  KZT списано с prepaid (amount−fee): {ms(melbet_credit_kzt)}")
print(f"  это USDT по курсу ордера:           {ms(melbet_booked)}")
print(f"  это USDT по курсу залива {BUY_MARKUP}:     {ms(melbet_real)}")
print(f"  ★ дыра:                             {ms(melbet_gap)} USDT")
print("  NET эту дыру не видит: доход посчитан по xe+5, а тенге куплены дороже.")

section("H2  Курс команды всё ещё не снят (другие люди, не PSP)")
print(f"  ★ ещё на балансах людей: {ms(human_fx_left)} USDT")
for name, val in sorted(by_trader_fx.items(), key=lambda kv: -kv[1]):
    print(f"    {name:20} n={by_trader_n[name]:4}  {ms(val)}")
if not by_trader_fx:
    print("    нет (resdfe/resdfe1 уже забраны отдельными проводками)")

section("H3  Сделки с отрицательной маржой (mdr + FX − trader − agent)")
print(f"  n={neg_n}  сумма={ms(neg_pnl)}")

section("Движения не из заявок (комментарии, топ по сумме)")
txs = (
    Transaction.objects.filter(creation_date__gte=since, creation_date__lt=now)
    .exclude(linked_in_order__isnull=False)
    .exclude(linked_out_order__isnull=False)
)
by_comment = defaultdict(lambda: ZERO)
n_comment = defaultdict(int)
for tx in txs.iterator(chunk_size=500):
    c = (tx.comment or "-")[:80]
    by_comment[c] += money(tx.value)
    n_comment[c] += 1
shown = 0
for c, val in sorted(by_comment.items(), key=lambda kv: -abs(kv[1])):
    if shown >= 25:
        break
    shown += 1
    print(f"  {ms(val):>12}  n={n_comment[c]:4}  {c}")
if shown == 0:
    print("  нет")

section("СВОДКА")
print(f"  NET за окно:                         {pnl['net']}")
print(f"  H1 Melbet xe+4.5 vs xe+5:            {ms(melbet_gap)}")
print(f"  H2 FX ещё у людей:                   {ms(human_fx_left)}")
print(f"  H3 минусовые сделки:                 {ms(neg_pnl)}")
print(f"  сумма дыр H1+H2+H3:                  {ms(melbet_gap + human_fx_left + (-neg_pnl if neg_pnl < 0 else ZERO))}")
print("DONE")
