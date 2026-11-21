"""Где маржа resdfe / resdfe1: xe+4 и 4% vs фактические проводки.

Гипотеза из кода (trade/models.py freeze/complete):
  живой трейдер (не PSP) Freeze и Charge = usd_amount (курс МЕРЧАНТА),
  а не psp_usd (xe+4). Commission = 4% × psp_usd.
  Разница psp_usd − merchant_usd остаётся на балансе команды — это и есть
  «0.5%», которые должны были быть маржой площадки.

  docker compose exec -T app \\
    python manage.py shell < titanpay/basics/shell_analyze_resdfe_margin_leak.py

  TRADERS=resdfe,resdfe1
  TARGET_XE=1.04
  MERCHANT_MDR=7          # ожидание в голове (сверка, не из ордера)
  TRADER_MDR=4
"""
from __future__ import annotations

import os
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from basics.models import Trader
from payments.dual_fx import merchant_fx_markup
from payments.psp_payin import is_psp_trader
from trade.models import CryptoDepositCredit, InOrder, OutOrder, Transaction

Q2 = Decimal("0.01")
Q3 = Decimal("0.001")
ZERO = Decimal("0.00")
TRADERS = [
    x.strip()
    for x in (os.environ.get("TRADERS") or "resdfe,resdfe1").split(",")
    if x.strip()
]
TARGET_XE = Decimal((os.environ.get("TARGET_XE") or "1.04").strip() or "1.04")
EXPECT_MERCH_MDR = Decimal((os.environ.get("MERCHANT_MDR") or "7").strip() or "7")
EXPECT_TRADER_MDR = Decimal((os.environ.get("TRADER_MDR") or "4").strip() or "4")


def money(raw) -> Decimal:
    return Decimal(str(raw or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def ms(raw) -> str:
    return f"{money(raw):,.2f}"


def section(t: str) -> None:
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)


def tx_maps(order_ids: list) -> tuple[dict, dict, dict]:
    """order_id → Charge completed / Commission / Teamlead."""
    charge: dict = defaultdict(lambda: ZERO)
    comm: dict = defaultdict(lambda: ZERO)
    tl: dict = defaultdict(lambda: ZERO)
    if not order_ids:
        return charge, comm, tl
    qs = Transaction.objects.filter(linked_in_order_id__in=order_ids).filter(
        comment__in=["In-order completed", "Commission", "Teamlead commission"]
    ).values("linked_in_order_id", "comment", "transaction_type__name").annotate(s=Sum("value"))
    for row in qs:
        oid = row["linked_in_order_id"]
        val = money(row["s"])
        if row["comment"] == "In-order completed" and row["transaction_type__name"] == "Charge":
            charge[oid] += val
        elif row["comment"] == "Commission" and row["transaction_type__name"] == "Deposit":
            comm[oid] += val
        elif row["comment"] == "Teamlead commission":
            tl[oid] += val
    return charge, comm, tl


def merchant_fee_usd(order) -> Decimal:
    fee = Decimal(str(order.merchant_fee or 0))
    amount = Decimal(str(order.amount or 0))
    usd = Decimal(str(order.usd_amount or 0))
    if amount <= 0 or usd <= 0:
        return money(fee)
    # Melbet: fee в фиате (обычно >> usd)
    if fee > usd:
        return money(fee * usd / amount)
    return money(fee)


def expected_psp(order) -> Decimal:
    """psp_usd как если бы трейдер был xe+TARGET_XE, от курса мерчанта на ордере."""
    amount = Decimal(str(order.amount or 0))
    usd = Decimal(str(order.usd_amount or 0))
    if amount <= 0 or usd <= 0:
        return money(usd)
    ps = order.solution.payment_system if order.solution_id else None
    merch = order.solution.merchant if order.solution_id else None
    mm = merchant_fx_markup(ps, merchant=merch)
    mr = Decimal(str(getattr(order, "merchant_rate", 0) or 0))
    if mr <= 0:
        mr = (amount / usd).quantize(Q3, rounding=ROUND_HALF_UP)
    if mm <= 0 or TARGET_XE <= 0 or mr <= 0:
        return money(usd)
    psp_rate = (mr * TARGET_XE / mm).quantize(Q3, rounding=ROUND_HALF_UP)
    if psp_rate <= 0:
        return money(usd)
    return money(amount / psp_rate)


section("КОД: почему 0.5% может остаться у команды")
print("  freeze()  и complete() для НЕ-PSP трейдера списывают usd_amount")
print("  (курс мерчанта), а не psp_usd (xe+4).")
print("  Commission возвращает trader_fee = mdr_in% × psp_usd.")
print("  FX = psp − merchant НЕ снимается с баланса команды.")
print(f"  is_psp_trader(resdfe*) ожидаем False — проверим ниже.")

grand = defaultdict(lambda: ZERO)
grand_n = 0

for username in TRADERS:
    trader = (
        Trader.objects.select_related("user", "team", "balance_usdt", "frozen_balance_usdt")
        .filter(user__username=username)
        .first()
    )
    section(f"ТРЕЙДЕР {username}")
    if trader is None:
        print("  NOT FOUND")
        continue
    psp_flag = is_psp_trader(trader)
    tl_pct = Decimal(str(trader.team.teamlead_percentage or 0)) if trader.team_id else ZERO
    print(f"  team={trader.team.name if trader.team_id else None}")
    print(f"  is_psp_trader={psp_flag}  (False → Charge=merchant usd, FX не снимается)")
    print(f"  teamlead_percentage={tl_pct}% от usd_amount")
    av = money(trader.balance_usdt.amount if trader.balance_usdt_id else 0)
    fr = money(trader.frozen_balance_usdt.amount if trader.frozen_balance_usdt_id else 0)
    print(f"  LK available={ms(av)}  frozen={ms(fr)}  owed≈{ms(av + fr)}")

    orders = (
        InOrder.objects.filter(
            status__name="Completed",
            payment_details__group__trader=trader,
        )
        .select_related(
            "solution__payment_system",
            "solution__merchant__user",
            "payment_details__group__trader",
        )
        .order_by("completion_date")
    )
    first = orders.first()
    last = orders.last()
    print(
        f"  completed IN: {orders.count()}  "
        f"first={first.completion_date if first else None}  "
        f"last={last.completion_date if last else None}"
    )

    b = defaultdict(lambda: ZERO)
    st = {"n": 0, "fx": 0, "eq_usd": 0, "eq_psp": 0, "other": 0}
    by_merch = defaultdict(lambda: defaultdict(lambda: ZERO))

    chunk: list = []

    def consume(batch: list) -> None:
        if not batch:
            return
        charge_m, comm_m, tl_m = tx_maps([o.id for o in batch])
        for order in batch:
            st["n"] += 1
            usd = money(order.usd_amount)
            stored_psp = money(order.psp_usd_amount)
            actual_psp = stored_psp if stored_psp > 0 else usd
            target_psp = expected_psp(order)
            charged = charge_m[order.id]
            comm = comm_m[order.id]
            tl = tl_m[order.id]
            mfee = merchant_fee_usd(order)
            booked_fx = money(actual_psp - usd)
            target_fx = money(target_psp - usd)
            # Сколько FX осталось у трейдера: должны были списать target_psp, списали charged
            leak_vs_target = money(target_psp - charged) if charged > 0 else target_fx
            leak_vs_booked = money(actual_psp - charged) if charged > 0 else booked_fx

            b["usd"] += usd
            b["stored_psp"] += actual_psp
            b["target_psp"] += target_psp
            b["charged"] += charged
            b["comm"] += comm
            b["tl"] += tl
            b["mfee"] += mfee
            b["booked_fx"] += booked_fx
            b["target_fx"] += target_fx
            b["leak_booked"] += leak_vs_booked
            b["leak_target"] += leak_vs_target
            b["amount"] += money(order.amount)
            if booked_fx >= Decimal("0.01"):
                st["fx"] += 1
            if charged <= 0:
                st["other"] += 1
            elif abs(charged - usd) < Decimal("0.02") and abs(charged - actual_psp) >= Decimal("0.02"):
                st["eq_usd"] += 1
            elif abs(charged - actual_psp) < Decimal("0.02") and actual_psp > usd + Decimal("0.02"):
                st["eq_psp"] += 1
            elif abs(charged - usd) < Decimal("0.02"):
                st["eq_usd"] += 1
            else:
                st["other"] += 1

            mu = "-"
            try:
                mu = order.solution.merchant.user.username
            except Exception:
                pass
            by_merch[mu]["n"] += 1
            by_merch[mu]["usd"] += usd
            by_merch[mu]["mfee"] += mfee
            by_merch[mu]["leak"] += leak_vs_target
            by_merch[mu]["comm"] += comm

    for order in orders.iterator(chunk_size=400):
        chunk.append(order)
        if len(chunk) >= 400:
            consume(chunk)
            chunk = []
    consume(chunk)

    # crypto top-ups
    credits = money(
        CryptoDepositCredit.objects.filter(wallet__trader=trader, credited=True).aggregate(s=Sum("amount"))["s"]
        or 0
    )
    # all deposits onto available that look like crypto / manual (not Commission)
    dep_other = money(
        Transaction.objects.filter(
            to_balance_id=trader.balance_usdt_id,
            transaction_type__name="Deposit",
        )
        .exclude(comment="Commission")
        .exclude(comment__icontains="unfreeze")
        .exclude(comment__icontains="Release leftover")
        .exclude(comment__icontains="expired")
        .aggregate(s=Sum("value"))["s"]
        or 0
    )

    outs = OutOrder.objects.filter(
        status__name="Completed",
        payment_details__group__trader=trader,
    )
    out_usd = money(outs.aggregate(s=Sum("usd_amount"))["s"] or 0)
    out_fee = money(outs.aggregate(s=Sum("trader_fee"))["s"] or 0)
    out_n = outs.count()

    # What platform SHOULD have kept on these INs
    # mfee + target_fx − trader_fee_on_target − agent
    # We don't recompute agent; use stored agent_fee sum
    agent = money(
        orders.aggregate(s=Sum("agent_fee"))["s"] or 0
    )
    expect_fee_on_target = money(b["target_psp"] * EXPECT_TRADER_MDR / Decimal(100))
    # stored commission is actual paid
    should_pnl = money(b["mfee"] + b["target_fx"] - expect_fee_on_target - agent)
    # "actual" if we only count what left the trader beyond fee:
    # charged - comm  is what trader net-lost; platform margin vs 7/4 is separate
    trader_net_out = money(b["charged"] - b["comm"])  # USDT left trader on completes (before TL)
    # If we had charged target_psp, trader net-out would be target_psp - expect_fee
    trader_should_out = money(b["target_psp"] - expect_fee_on_target)

    print(f"\n  ОБОРОТ IN")
    print(f"    n={st['n']}  fiat={ms(b['amount'])}")
    print(f"    merchant USD (списано с учёта мерча): {ms(b['usd'])}")
    print(f"    psp USD как записан на ордере:        {ms(b['stored_psp'])}")
    print(f"    psp USD если бы xe+{TARGET_XE}:         {ms(b['target_psp'])}")
    print(f"    Charge с frozen (факт леджера):       {ms(b['charged'])}")
    print(f"    Commission назад на ЛК:               {ms(b['comm'])}")
    print(f"    Teamlead с ЛК:                        {ms(b['tl'])}")
    print(f"    merchant fee USDT-экв:                {ms(b['mfee'])}")
    print(f"    agent_fee:                            {ms(agent)}")
    print(f"\n  КУРС")
    print(f"    FX записанный (psp−usd):              {ms(b['booked_fx'])}  на {st['fx']} заявках")
    print(f"    FX до xe+{TARGET_XE} (target−usd):       {ms(b['target_fx'])}")
    print(f"    Charge≈merchant usd (FX не снят):     {st['eq_usd']}")
    print(f"    Charge≈psp usd (FX снят):             {st['eq_psp']}")
    print(f"    Charge другое/0:                      {st['other']}")
    print(f"\n  УТЕЧКА К ТРЕЙДЕРУ")
    print(f"    ★ FX не снят vs записанный psp:       {ms(b['leak_booked'])} USDT")
    print(f"    ★ FX не снят vs xe+{TARGET_XE}:          {ms(b['leak_target'])} USDT")
    print(f"    трейдер отдал net (charge−fee):      {ms(trader_net_out)}")
    print(f"    должен был отдать (target−4%):       {ms(trader_should_out)}")
    print(f"    разница (осталось у трейдера):       {ms(trader_should_out - trader_net_out)}")
    print(f"\n  МАРЖА ПЛОЩАДКИ (оценка)")
    pct_m = (b["mfee"] * 100 / b["usd"]) if b["usd"] else ZERO
    pct_t = (b["comm"] * 100 / b["usd"]) if b["usd"] else ZERO
    print(f"    факт MDR мерча / оборот:              {pct_m:.2f}%  (ожидание {EXPECT_MERCH_MDR}%)")
    print(f"    факт fee трейдера / merchant usd:     {pct_t:.2f}%  (ожидание {EXPECT_TRADER_MDR}%)")
    print(f"    PnL если снять xe+{TARGET_XE} и fee {EXPECT_TRADER_MDR}%: {ms(should_pnl)}")
    print(f"    PnL БЕЗ FX (только mfee−comm−agent):  {ms(b['mfee'] - b['comm'] - agent)}")
    print(f"\n  ДЕНЬГИ НА ЛК")
    print(f"    CryptoDepositCredit:                  {ms(credits)}")
    print(f"    прочие Deposit на available:          {ms(dep_other)}")
    print(f"    OUT completed n={out_n} usd={ms(out_usd)} trader_fee={ms(out_fee)}")
    print(f"    сейчас available+frozen:              {ms(av + fr)}")

    print(f"\n  ПО МЕРЧАНТАМ")
    for mu, row in sorted(by_merch.items(), key=lambda kv: -kv[1]["usd"]):
        print(
            f"    {mu:16} n={int(row['n']):5}  usd={ms(row['usd']):>12}  "
            f"mfee={ms(row['mfee']):>10}  comm={ms(row['comm']):>10}  "
            f"fx_leak_vs_xe4={ms(row['leak']):>10}"
        )

    for k, v in b.items():
        grand[k] += v
    grand["agent"] += agent
    grand["credits"] += credits
    grand["owed"] += av + fr
    grand_n += st["n"]

section("ИТОГО " + ",".join(TRADERS))
print(f"  заявок IN:                 {grand_n}")
print(f"  merchant USD:              {ms(grand['usd'])}")
print(f"  Charge факт:               {ms(grand['charged'])}")
print(f"  Commission:                {ms(grand['comm'])}")
print(f"  Teamlead:                  {ms(grand['tl'])}")
print(f"  merchant fee USDT:         {ms(grand['mfee'])}")
print(f"  agent:                     {ms(grand['agent'])}")
print(f"  ★ FX остался у трейдеров vs xe+{TARGET_XE}: {ms(grand['leak_target'])} USDT")
print(f"  ★ FX остался vs записанный psp:            {ms(grand['leak_booked'])} USDT")
print(f"  crypto credited:           {ms(grand['credits'])}")
print(f"  LK owed сейчас:            {ms(grand['owed'])}")
print()
print("  ГИПОТЕЗЫ")
print("  H1 Charge=merchant usd, не xe+4. Если leak_target >> 0 и charge≈usd — ПОДТВЕРЖДЕНО.")
print("     Это не двойное списание. Площадка не забирает курсовую разницу с команды.")
print("  H2 Ставка 4% платится, но от базы, а списание оборота — по курсу мерча (меньше).")
print("     Команда получает fee и не отдаёт лишние ~0.5–1% USDT.")
print("  H3 Если mfee/оборот << 7% — мерч платит меньше, чем в голове; это отдельная дыра.")
print("  H4 Teamlead % от оборота режется с команды, не с маржи площадки напрямую.")
print("  H5 Crypto top-up увеличивает долг 1:1, прибыль не забирает.")
print("DONE")
