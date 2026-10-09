"""
Melbet KGS balance (balance_kgs / frozen_balance_kgs).

  docker compose exec -T app python manage.py shell < titanpay/basics/shell_melbet_kgs_balance.py

  MERCHANT_USERNAME=melbet SET=0
  MERCHANT_USERNAME=melbet DELTA=10000
"""
from __future__ import annotations

import os
from decimal import Decimal

from merchant.kzt_settlement import (
    MELBET_TEST_USERNAME,
    MELBET_USERNAME,
    ensure_kgs_balances,
    get_melbet_merchant,
)

uname = os.environ.get("MERCHANT_USERNAME", MELBET_USERNAME).strip() or MELBET_USERNAME
if uname == MELBET_TEST_USERNAME:
    pass

m = get_melbet_merchant(uname)
if m is None:
    print(f"merchant {uname} not found")
else:
    ensure_kgs_balances(m)
    m.refresh_from_db()
    print(f"[{uname}] balance_kgs:        {m.balance_kgs.amount}")
    print(f"[{uname}] frozen_balance_kgs: {m.frozen_balance_kgs.amount}")
    raw_set = os.environ.get("SET")
    raw_delta = os.environ.get("DELTA")
    if raw_set not in (None, ""):
        m.balance_kgs.amount = Decimal(str(raw_set))
        m.balance_kgs.save(update_fields=["amount"])
        print(f"[{uname}] SET balance_kgs={m.balance_kgs.amount}")
    elif raw_delta not in (None, ""):
        m.balance_kgs.amount += Decimal(str(raw_delta))
        m.balance_kgs.save(update_fields=["amount"])
        print(f"[{uname}] DELTA -> balance_kgs={m.balance_kgs.amount}")
