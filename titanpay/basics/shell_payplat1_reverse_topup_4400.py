"""
Откатить ошибочное пополнение payplat1 на 4400 USDT.

Случайный admin-bot: «пополни провайдера payplat1 4400 …».
Ledger тот же, что у «списать провайдера»: Charge balance_usdt → chain (type=3).

Осмотр:
  docker compose exec -T -e DRY_RUN=1 app python manage.py shell \\
    < titanpay/basics/shell_payplat1_reverse_topup_4400.py

Списание:
  docker compose exec -T -e DRY_RUN=0 app python manage.py shell \\
    < titanpay/basics/shell_payplat1_reverse_topup_4400.py

Из контейнера (/app):
  DRY_RUN=1 python manage.py shell < basics/shell_payplat1_reverse_topup_4400.py
  DRY_RUN=0 python manage.py shell < basics/shell_payplat1_reverse_topup_4400.py

Переопределение: AMOUNT, USERNAME, COMMENT.
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from basics.models import Balance, Trader
from trade.models import Transaction, TransactionType

DRY_RUN = os.environ.get("DRY_RUN", "1").strip().lower() not in ("0", "false", "no")
USERNAME = os.environ.get("USERNAME", "payplat1").strip() or "payplat1"
AMOUNT = Decimal(os.environ.get("AMOUNT", "4400")).quantize(Decimal("0.01"))
COMMENT = os.environ.get(
    "COMMENT",
    "admin ошибочное пополнение 4400",
).strip()[:256]


def _recent(balance: Balance, limit: int = 15):
    return list(
        Transaction.objects.filter(Q(from_balance=balance) | Q(to_balance=balance))
        .select_related("transaction_type")
        .order_by("-creation_date")[:limit]
    )


def _side(tx: Transaction, balance: Balance) -> str:
    if tx.to_balance_id == balance.id:
        return f"+{tx.value}"
    if tx.from_balance_id == balance.id:
        return f"-{tx.value}"
    return str(tx.value)


def run() -> None:
    print("=" * 64)
    print("payplat1 reverse excess top-up (Charge → chain type=3)")
    print("=" * 64)
    print(f"  username: {USERNAME}")
    print(f"  amount:   {AMOUNT} USDT")
    print(f"  comment:  {COMMENT}")
    print(f"  dry_run:  {DRY_RUN}")

    trader = (
        Trader.objects.select_related("user", "balance_usdt")
        .filter(user__username__iexact=USERNAME)
        .first()
    )
    if trader is None or trader.balance_usdt_id is None:
        raise SystemExit(f"провайдер/трейдер {USERNAME!r} не найден или без balance_usdt")

    bal = trader.balance_usdt
    before = Decimal(str(bal.amount))
    print(f"  trader_id: {trader.id}")
    print(f"  balance_usdt: {before}  (id={bal.id})")
    print(f"  after charge: {before - AMOUNT}")

    print()
    print("  last ledger rows on balance_usdt:")
    for tx in _recent(bal):
        tname = tx.transaction_type.name if tx.transaction_type_id else "?"
        print(
            f"    {tx.creation_date}  {_side(tx, bal):>14}  "
            f"{tname:<10}  id={tx.id}  {tx.comment}"
        )

    same_deposits = list(
        Transaction.objects.filter(
            to_balance=bal,
            value=AMOUNT,
            transaction_type__name="Deposit",
        ).order_by("-creation_date")[:8]
    )
    if same_deposits:
        print()
        print(f"  recent Deposit {AMOUNT} → balance_usdt (likely the mistaken top-up):")
        for tx in same_deposits:
            print(f"    {tx.creation_date}  +{tx.value}  id={tx.id}  {tx.comment}")

    dup = Transaction.objects.filter(
        from_balance=bal,
        value=AMOUNT,
        comment=COMMENT,
        transaction_type__name="Charge",
    ).first()
    if dup:
        raise SystemExit(f"Already charged (id={dup.id}) — abort to avoid double write-off")

    if before < AMOUNT:
        raise SystemExit(
            f"Недостаточно средств на balance_usdt: есть {before}, нужно списать {AMOUNT}"
        )

    if DRY_RUN:
        print()
        print("DRY_RUN=1 — nothing written. Re-run with DRY_RUN=0 to charge.")
        print(
            "Или в admin-боте: "
            f"списать провайдера {USERNAME} {AMOUNT} ошибочное пополнение"
        )
        return

    chain = Balance.objects.get(type=3)
    charge_type = TransactionType.objects.get(name="Charge")
    with transaction.atomic():
        tx = Transaction.create(
            _from=bal,
            _to=chain,
            value=AMOUNT,
            _transaction_type=charge_type,
            _comment=COMMENT,
        )
        bal.refresh_from_db()
        print()
        print(f"  booked Charge id={tx.id}  -{tx.value}")
        print(f"  balance_usdt now: {bal.amount}")
        print("DONE")


run()
