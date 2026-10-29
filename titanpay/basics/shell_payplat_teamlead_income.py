"""
Оборот payplat1 за всё время + доход его тимлида (начисления / выводы / баланс).

  docker-compose exec -T app python3 manage.py shell < titanpay/basics/shell_payplat_teamlead_income.py
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

from basics.models import Trader
from trade.models import InOrder, OutOrder, Transaction, WithdrawalRequest

Q2 = Decimal("0.01")
TRADER = "payplat1"


def money(v) -> Decimal:
    return (v or Decimal("0")).quantize(Q2, rounding=ROUND_HALF_UP)


def agg_orders(qs, *, with_psp: bool):
    kwargs = dict(n=Count("id"), fiat=Sum("amount"), usd=Sum("usd_amount"), fee=Sum("trader_fee"))
    if with_psp:
        kwargs["psp"] = Sum(Coalesce("psp_usd_amount", "usd_amount"))
    row = qs.aggregate(**kwargs)
    usd = money(row["usd"])
    return {
        "n": row["n"] or 0,
        "fiat": money(row["fiat"]),
        "usd": usd,
        "psp": money(row["psp"]) if with_psp else usd,
        "fee": money(row["fee"]),
    }


trader = Trader.objects.select_related(
    "user",
    "team",
    "team__teamlead",
    "team__teamlead__user",
    "team__teamlead__balance",
    "team__teamlead__frozen_balance",
    "balance_usdt",
).get(user__username=TRADER)
team = trader.team
tl = team.teamlead
if tl is None:
    raise RuntimeError("у payplat1 нет тимлида")

pct = Decimal(str(team.teamlead_percentage or 0))
ins = agg_orders(
    InOrder.objects.filter(payment_details__group__trader=trader, status__name="Completed"),
    with_psp=True,
)
outs = agg_orders(
    OutOrder.objects.filter(payment_details__group__trader=trader, status__name="Completed"),
    with_psp=False,
)

comm_in = Transaction.objects.filter(
    to_balance=tl.balance,
    comment="Teamlead commission",
    linked_in_order__payment_details__group__trader=trader,
)
comm_out = Transaction.objects.filter(
    to_balance=tl.balance,
    comment="Teamlead commission",
    linked_out_order__payment_details__group__trader=trader,
)
other_comm = Transaction.objects.filter(
    to_balance=tl.balance,
    comment__icontains="Teamlead commission",
).exclude(
    Q(linked_in_order__payment_details__group__trader=trader)
    | Q(linked_out_order__payment_details__group__trader=trader)
)
corr = Transaction.objects.filter(to_balance=tl.balance).exclude(
    comment="Teamlead commission"
).filter(comment__icontains="teamlead")

paid_in = money(comm_in.aggregate(v=Sum("value"))["v"])
paid_out = money(comm_out.aggregate(v=Sum("value"))["v"])
paid_other = money(other_comm.aggregate(v=Sum("value"))["v"])
paid_corr = money(corr.aggregate(v=Sum("value"))["v"])
paid_payplat = money(paid_in + paid_out)
expected_in = money(ins["fee"] * pct / Decimal("100"))
expected_out = money(outs["fee"] * pct / Decimal("100"))

avail = money(tl.balance.amount if tl.balance_id else 0)
frozen = money(tl.frozen_balance.amount if tl.frozen_balance_id else 0)
wrs = WithdrawalRequest.objects.filter(Q(balance=tl.balance) | Q(from_user=tl.user))
wr = {0: Decimal("0"), 1: Decimal("0"), 2: Decimal("0")}
wr_n = {0: 0, 1: 0, 2: 0}
for item in wrs:
    wr[item.status] = money(wr[item.status] + Decimal(str(item.amount)))
    wr_n[item.status] += 1
# pending уже в frozen; earned = available + frozen + approved
earned = money(avail + frozen + wr[1])

print("=== PAYPLAT1 ===")
print(f"trader:     {trader.user.username}  available={money(trader.balance_usdt.amount)}")
print(f"team:       {team.name}  mdr rate_in={team.rate_in}%  teamlead_percentage={pct}% от trader_fee")
print(f"формула:    teamlead = trader_fee * {pct}% / 100")
print(f"            trader_fee IN = mdr_in * psp_usd / 100  (не merchant usd)")
print()
print("=== ОБОРОТ COMPLETED, ВСЁ ВРЕМЯ ===")
print(f"IN  {ins['n']:6} шт  fiat={ins['fiat']}  merchant_usd={ins['usd']}  psp_usd={ins['psp']}  trader_fee={ins['fee']}")
print(f"OUT {outs['n']:6} шт  fiat={outs['fiat']}  merchant_usd={outs['usd']}  psp_usd={outs['psp']}  trader_fee={outs['fee']}")
print(f"IN+OUT merchant_usd={money(ins['usd']+outs['usd'])}  psp_usd={money(ins['psp']+outs['psp'])}")
print()
print("=== ТИМЛИД", tl.user.username, "===")
print(f"available:           {avail}")
print(f"frozen:              {frozen}")
print(f"WR pending (0):      {wr[0]}  n={wr_n[0]}   (сидит в frozen, не плюсовать ещё раз)")
print(f"WR approved (1):     {wr[1]}  n={wr_n[1]}")
print(f"WR rejected (2):     {wr[2]}  n={wr_n[2]}")
print(f"заработал всего:     {earned}  = available + frozen + approved WR")
print()
print("=== СВЕРКА НАЧИСЛЕНИЙ С PAYPLAT1 ===")
print(f"ожидали IN  (fee*{pct}%): {expected_in}")
print(f"ожидали OUT (fee*{pct}%): {expected_out}")
print(f"ожидали IN+OUT:           {money(expected_in+expected_out)}")
print(f"факт Teamlead commission IN:  {paid_in}  n={comm_in.count()}")
print(f"факт Teamlead commission OUT: {paid_out}  n={comm_out.count()}")
print(f"факт с payplat1:              {paid_payplat}  delta={money(paid_payplat - expected_in - expected_out)}")
print(f"комиссии с ДРУГИХ трейдеров:  {paid_other}  n={other_comm.count()}")
print(f"прочие teamlead tx:           {paid_corr}  n={corr.count()}")
print()
print("delta ≠ 0 — либо ставка менялась по ходу, либо комиссия шла от psp_usd,")
print("а сверка fee уже после пересчётов. Смотри merchant_usd vs psp_usd выше.")
print("0.2%/0.4% от оборота — это договорённость, в коде доля от trader_fee.")
