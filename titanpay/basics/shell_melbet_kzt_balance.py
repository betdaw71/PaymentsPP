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

from merchant.kzt_settlement import MELBET_TEST_USERNAME, MELBET_USERNAME, ensure_kzt_balances, get_melbet_merchant

# melbet_test на стенде, если нет доступа к prod melbet
DEFAULT_USERNAME = MELBET_TEST_USERNAME


def _merchant(username: str | None = None):
    name = username or DEFAULT_USERNAME
    m = get_melbet_merchant(name)
    if m is None:
        raise RuntimeError(
            f"Merchant user '{name}' not found. "
            f"Создайте: exec(open('basics/shell_create_melbet_test_merchant.py').read()); run()"
        )
    return ensure_kzt_balances(m)


def show(username: str | None = None):
    m = _merchant(username)
    m.refresh_from_db()
    uname = m.user.username
    print(f"[{uname}] balance_kzt:        {m.balance_kzt.amount}")
    print(f"[{uname}] frozen_balance_kzt: {m.frozen_balance_kzt.amount}")
    print(f"[{uname}] balance USDT:       {m.balance.amount if m.balance else None}")


def set_balance(value: str | Decimal, username: str | None = None):
    m = _merchant(username)
    m.balance_kzt.amount = Decimal(str(value))
    m.balance_kzt.save(update_fields=["amount"])
    show()


def add_balance(delta: str | Decimal, username: str | None = None):
    m = _merchant(username)
    m.balance_kzt.amount += Decimal(str(delta))
    m.balance_kzt.save(update_fields=["amount"])
    show()


def run():
    show()


if __name__ == "__main__":
    run()
else:
    print(
        "Run: run() | set_balance('-2000000') | add_balance('100000') | show() | "
        f"set_balance('0', username='{MELBET_USERNAME}')"
    )
