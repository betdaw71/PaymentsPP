"""
Melbet KZT balance (balance_kzt / frozen_balance_kzt).

  docker compose exec app python manage.py shell

  exec(open("basics/shell_melbet_kzt_balance.py").read())
  run()                    # ensure accounts + print
  set_balance("-2000000")  # предоплата в минусе
  add_balance("500000")    # пополнение (движение к нулю)
"""
from __future__ import annotations

from decimal import Decimal

from merchant.kzt_settlement import ensure_kzt_balances, get_melbet_merchant


def _merchant():
    m = get_melbet_merchant()
    if m is None:
        raise RuntimeError("Merchant user 'melbet' not found")
    return ensure_kzt_balances(m)


def show():
    m = _merchant()
    m.refresh_from_db()
    print(f"melbet balance_kzt:      {m.balance_kzt.amount}")
    print(f"melbet frozen_balance_kzt: {m.frozen_balance_kzt.amount}")
    print(f"melbet balance USDT:     {m.balance.amount if m.balance else None}")


def set_balance(value: str | Decimal):
    m = _merchant()
    m.balance_kzt.amount = Decimal(str(value))
    m.balance_kzt.save(update_fields=["amount"])
    show()


def add_balance(delta: str | Decimal):
    m = _merchant()
    m.balance_kzt.amount += Decimal(str(delta))
    m.balance_kzt.save(update_fields=["amount"])
    show()


def run():
    show()


if __name__ == "__main__":
    run()
else:
    print("Run: run() | set_balance('-2000000') | add_balance('100000') | show()")
