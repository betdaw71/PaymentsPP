"""
LayerOne: мы должны провайдеру → пассив кассы (не prepaid-актив).

  1) layerone1 убран из PREPAID, добавлен в DEPOSIT_FROM_PSP (код).
  2) В ЛК баланс должен быть ПЛЮС (долг им). Сейчас часто минус из старой схемы.

  TARGET=100 \\
  docker compose exec -T -e TARGET app \\
    python manage.py shell < titanpay/basics/shell_set_layerone_cash_debt.py

  APPLY=1 — выставить balance_usdt = +TARGET.
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.db import transaction

from basics.models import Balance, Trader

TARGET = Decimal(str((os.environ.get("TARGET") or "100").strip() or "100"))
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
USERNAME = (os.environ.get("TRADER") or "layerone1").strip()


def main() -> None:
    t = (
        Trader.objects.select_related("user", "balance_usdt", "frozen_balance_usdt")
        .filter(user__username__iexact=USERNAME)
        .first()
    )
    if t is None:
        print(f"NOT FOUND {USERNAME}")
        return
    avail = Decimal(str(t.balance_usdt.amount if t.balance_usdt_id else 0))
    frozen = Decimal(str(t.frozen_balance_usdt.amount if t.frozen_balance_usdt_id else 0))
    print(f"{USERNAME}: LK avail={avail} frozen={frozen}")
    print(f"  cash role: DEPOSIT_FROM_PSP → liability = max(0, avail)")
    print(f"  target avail=+{TARGET} → liability {TARGET}")
    if avail == TARGET:
        print("already at target")
        return
    if not APPLY:
        print("DRY-RUN — set APPLY=1 to set balance_usdt to +TARGET")
        return
    with transaction.atomic():
        bal = Balance.objects.select_for_update().get(pk=t.balance_usdt_id)
        bal.amount = TARGET
        bal.save(update_fields=["amount"])
        print(f"SET {USERNAME} balance_usdt={bal.amount}")


main()
