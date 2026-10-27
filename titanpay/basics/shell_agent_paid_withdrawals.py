"""Сверка агентов + заявки на уже выплаченное вне ЛК (апрув в headsupport).

  docker-compose exec -T -e APPLY=1 \
    -e CARDSMG_AMOUNT=264 \
    -e L_PAYMENTS_AMOUNT=0 \
    app python3 manage.py shell < /app/basics/shell_agent_paid_withdrawals.py

Хеш в заявку не пишется: его ставишь при апруве в headsupport.
CardsMG tx:
  eb9ee76a6c4bafe7ebf523c8b7540aca0273710ea22241dcee86cdf2a097d833
"""
from __future__ import annotations

import os
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum

from merchant.models import Agent
from trade.models import InOrder, Transaction, WithdrawalRequest

PCT = Decimal("0.002")
Q2 = Decimal("0.01")
WALLET = "TEPKpVsAUyrkLx38ueFzSQP1HXGX8XK1Tt"
PLAN = (
    (
        "CardsMG",
        "pandapay",
        Decimal(os.environ.get("CARDSMG_AMOUNT") or "264"),
        "eb9ee76a6c4bafe7ebf523c8b7540aca0273710ea22241dcee86cdf2a097d833",
    ),
    (
        "L_payments",
        "melbet",
        Decimal(os.environ.get("L_PAYMENTS_AMOUNT") or "0"),
        (os.environ.get("L_PAYMENTS_TX") or "").strip(),
    ),
)
APPLY = os.environ.get("APPLY", "").strip() in ("1", "true", "yes")


def D(x) -> Decimal:
    return Decimal(str(x or 0)).quantize(Q2)


def diagnose(agent: Agent, merchant_name: str, offchain: Decimal) -> None:
    usd = InOrder.objects.filter(
        solution__merchant__user__username__iexact=merchant_name,
        status__name="Completed",
    ).aggregate(s=Sum("usd_amount"))["s"]
    usd = D(usd)
    fair = (usd * PCT).quantize(Q2)
    ids = [i for i in (agent.balance_id, agent.frozen_balance_id) if i]
    txs = Transaction.objects.filter(Q(to_balance_id__in=ids) | Q(from_balance_id__in=ids)).select_related(
        "transaction_type"
    )
    by = defaultdict(lambda: Decimal("0"))
    for tx in txs:
        name = (tx.transaction_type.name if tx.transaction_type_id else "") or "?"
        comment = (tx.comment or "")[:80]
        val = D(tx.value)
        if tx.to_balance_id == agent.balance_id:
            by[f"IN {name} | {comment}"] += val
        elif tx.from_balance_id == agent.balance_id:
            by[f"OUT {name} | {comment}"] += val
    live = D(
        Transaction.objects.filter(
            to_balance_id=agent.balance_id,
            comment="Agent commission",
        ).aggregate(s=Sum("value"))["s"]
    )
    backfill = D(
        Transaction.objects.filter(
            to_balance_id=agent.balance_id,
            comment__startswith="Agent commission backfill",
        ).aggregate(s=Sum("value"))["s"]
    )
    wr_out = D(
        Transaction.objects.filter(
            from_balance_id=agent.frozen_balance_id,
            transaction_type__name="Withdrawal",
        ).aggregate(s=Sum("value"))["s"]
    ) if agent.frozen_balance_id else D(0)
    lk = D(agent.balance.amount if agent.balance_id else 0)
    frozen = D(agent.frozen_balance.amount if agent.frozen_balance_id else 0)
    accrued = live + backfill
    overlap = D(accrued - fair) if accrued > fair else D(0)
    leftover_now = D(lk + frozen - fair)
    leftover_after_offchain = D(lk + frozen - offchain - fair)
    print(f"\n=== {agent.user.username} / {merchant_name} ===")
    print(f"  completed_usd={usd}  fair_0.2%={fair}")
    print(f"  live_commission={live}  backfill={backfill}  live+backfill={accrued}")
    print(f"  overlap_live_and_backfill={overlap}")
    print(f"  lk_available={lk}  lk_frozen={frozen}  lk_withdrawn={wr_out}")
    print(f"  offchain_to_write_off={offchain}")
    print(f"  leftover_vs_fair_now={leftover_now}  (плюс = лишнее в ЛК относительно 0.2%)")
    print(
        f"  leftover_after_this_wr={leftover_after_offchain}  "
        f"(после списания {offchain}: плюс = всё ещё лишнее, часто live+backfill на одни сделки)"
    )
    print("  ledger:")
    for key, val in sorted(by.items(), key=lambda kv: -abs(kv[1])):
        if val:
            print(f"    {val:>12}  {key}")
    wr = list(WithdrawalRequest.objects.filter(from_user=agent.user).order_by("-date")[:8])
    print("  withdrawals:")
    if not wr:
        print("    (none)")
    for item in wr:
        print(f"    {item.id} status={item.status} amount={item.amount} addr={item.address_to} tx={item.comment!r}")


def make_request(agent: Agent, amount: Decimal) -> WithdrawalRequest | None:
    amount = D(amount)
    if amount <= 0:
        print(f"  skip {agent.user.username}: amount 0")
        return None
    pending = WithdrawalRequest.objects.filter(from_user=agent.user, status=0, amount=amount).first()
    if pending:
        print(f"  already pending {pending.id} {agent.user.username} {amount}")
        return pending
    if not APPLY:
        print(f"  DRY {agent.user.username} would create {amount} → {WALLET}")
        return None
    req = WithdrawalRequest.create(
        amount=amount,
        _from=agent.balance,
        address_to=WALLET,
        from_user=agent.user,
    )
    print(f"  CREATED {req.id} {agent.user.username} {amount} addr={WALLET}")
    return req


print(f"APPLY={int(APPLY)} wallet={WALLET}", flush=True)
created = []
for agent_name, merchant_name, amount, tx_hash in PLAN:
    agent = Agent.objects.select_related("user", "balance", "frozen_balance").filter(user__username=agent_name).first()
    if agent is None:
        print(f"\n{agent_name}: NOT FOUND")
        continue
    diagnose(agent, merchant_name, D(amount))
    with transaction.atomic():
        req = make_request(agent, amount)
    if req is not None:
        created.append((req, tx_hash))
        if tx_hash:
            print(f"  approve in headsupport with tx id:\n    {tx_hash}")

print("\n=== REQUESTS ===")
if not created and not APPLY:
    print("DRY-RUN. APPLY=1 создаёт заявки. L_payments: сумма вне ЛК так и не была в чате — L_PAYMENTS_AMOUNT=0")
for req, tx_hash in created:
    extra = f"  approve_tx={tx_hash}" if tx_hash else "  approve_tx=UNKNOWN"
    print(f"  {req.from_user.username}  {req.amount}  id={req.id}{extra}")
