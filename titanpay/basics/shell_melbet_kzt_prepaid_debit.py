"""
Списать Melbet ₸ (balance_kzt) в минус за prepaid USDT.

Модель: предоплата USDT конвертируется по курсу и ДЕБЕТУЕТ balance_kzt
(уходит дальше в минус). Завершённые pay-in, наоборот, кредитуют ₸.
Не использовать credit_melbet_crypto_deposit — он начисляет ₸.

Текущий прогон по умолчанию: 6000 USDT × 475.851 (XE 455.36 + 4.5%) = 2 855 106.00 KZT.

Сначала осмотр:
  docker compose exec -T -e DRY_RUN=1 -e USDT=6000 -e RATE=475.851 app python manage.py shell \
    < titanpay/basics/shell_melbet_kzt_prepaid_debit.py

Списание:
  docker compose exec -T -e DRY_RUN=0 -e USDT=6000 -e RATE=475.851 app python manage.py shell \
    < titanpay/basics/shell_melbet_kzt_prepaid_debit.py

Из контейнера (/app):
  DRY_RUN=1 USDT=6000 RATE=475.851 python manage.py shell < basics/shell_melbet_kzt_prepaid_debit.py
  DRY_RUN=0 USDT=6000 RATE=475.851 python manage.py shell < basics/shell_melbet_kzt_prepaid_debit.py

Переопределение: USDT, RATE, MERCHANT_USERNAME, COMMENT, DRY_RUN.
"""
from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q

from basics.models import Balance
from merchant.kzt_settlement import (
    debit_melbet_crypto_prepaid,
    ensure_kzt_balances,
    get_melbet_merchant,
)
from trade.models import Transaction

DRY_RUN = os.environ.get("DRY_RUN", "1").strip().lower() not in ("0", "false", "no")
MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "melbet").strip() or "melbet"
USDT = Decimal(os.environ.get("USDT", "6000"))
RATE = Decimal(os.environ.get("RATE", "475.851"))
KZT = (USDT * RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
COMMENT = os.environ.get(
    "COMMENT",
    f"Manual crypto prepaid {USDT} USDT @ {RATE} = {KZT} KZT",
).strip()


def _recent_kzt_txs(balance: Balance, limit: int = 12):
    return list(
        Transaction.objects.filter(Q(from_balance=balance) | Q(to_balance=balance))
        .select_related("transaction_type")
        .order_by("-creation_date")[:limit]
    )


def _tx_side(tx: Transaction, balance: Balance) -> str:
    if tx.to_balance_id == balance.id:
        return f"+{tx.value}"
    if tx.from_balance_id == balance.id:
        return f"-{tx.value}"
    return str(tx.value)


def run() -> None:
    print("=" * 64)
    print("Melbet KZT prepaid DEBIT (further into minus)")
    print("=" * 64)
    print(f"  merchant: {MERCHANT_USERNAME}")
    print(f"  usdt:     {USDT}")
    print(f"  rate:     {RATE}")
    print(f"  kzt:      {KZT}")
    print(f"  comment:  {COMMENT}")
    print(f"  dry_run:  {DRY_RUN}")

    merchant = get_melbet_merchant(MERCHANT_USERNAME)
    if merchant is None:
        raise SystemExit(f"Merchant {MERCHANT_USERNAME!r} not found")
    merchant = ensure_kzt_balances(merchant)
    merchant.refresh_from_db()
    kzt = merchant.balance_kzt
    print(f"  merchant_id: {merchant.id}")
    print(f"  balance_kzt: {kzt.amount}  (id={kzt.id})")
    print(f"  after debit: {kzt.amount - KZT}")
    print()
    print("  last ledger rows on balance_kzt:")
    for tx in _recent_kzt_txs(kzt):
        print(
            f"    {tx.creation_date}  {_tx_side(tx, kzt):>14}  "
            f"id={tx.id}  {tx.comment}"
        )

    dup = Transaction.objects.filter(from_balance=kzt, comment=COMMENT, value=KZT).first()
    if dup:
        raise SystemExit(f"Already booked (id={dup.id}) — abort to avoid double debit")

    wrong_credit = Transaction.objects.filter(to_balance=kzt, value=KZT).order_by("-creation_date")[:5]
    if wrong_credit:
        print()
        print("  ! same amount already CREDITED to balance_kzt (wrong direction if prepaid):")
        for tx in wrong_credit:
            print(f"    {tx.creation_date}  +{tx.value}  id={tx.id}  {tx.comment}")
        print("  If that was a mistaken credit, roll it back separately; this script only DEBITS.")

    if DRY_RUN:
        print()
        print("DRY_RUN=1 — nothing written. Re-run with DRY_RUN=0 to debit.")
        return

    with transaction.atomic():
        tx = debit_melbet_crypto_prepaid(
            merchant,
            usdt_amount=USDT,
            rate=RATE,
            comment=COMMENT,
        )
        merchant.balance_kzt.refresh_from_db()
        print()
        print(f"  booked tx id={tx.id}  -{tx.value}")
        print(f"  balance_kzt now: {merchant.balance_kzt.amount}")
        print("DONE")


run()
