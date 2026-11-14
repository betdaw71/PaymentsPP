"""
Клонирование трейдера resdfe → resdfe1 в ту же команду (тот же тимлид)
с кастомным TRC20-кошельком для пополнений.

Запуск на сервере:
  docker compose exec app python manage.py shell < basics/shell_clone_trader_resdfe1.py

Или:
  docker compose exec -T app python manage.py shell < basics/shell_clone_trader_resdfe1.py
"""
from __future__ import annotations

import secrets
import string
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.authtoken.models import Token

from basics.models import Balance, Trader
from sms.models import TraderDevice
from trade.models import Address

SOURCE_LOOKUP = "resdfe"
TARGET_USERNAME = "resdfe1"
TARGET_TELEGRAM = "resdfe1"
DEPOSIT_ADDRESS = "TJtxY4nnixqBGMf1PMqFokH8HirHxH7eXC"


def _find_source(lookup: str) -> Trader:
    clean = lookup.lstrip("@").strip()
    trader = (
        Trader.objects.select_related(
            "user", "team", "team__teamlead", "team__teamlead__user",
            "language", "currency", "boss", "boss__user", "balance_usdt",
        )
        .filter(user__username__iexact=clean)
        .first()
    )
    if trader is None:
        trader = (
            Trader.objects.select_related(
                "user", "team", "team__teamlead", "team__teamlead__user",
                "language", "currency", "boss", "boss__user", "balance_usdt",
            )
            .filter(telegram__iexact=clean)
            .first()
        )
    if trader is None:
        trader = (
            Trader.objects.select_related(
                "user", "team", "team__teamlead", "team__teamlead__user",
                "language", "currency", "boss", "boss__user", "balance_usdt",
            )
            .filter(telegram__iexact=f"@{clean}")
            .first()
        )
    if trader is None:
        raise SystemExit(f"Source trader '{lookup}' not found (username/telegram).")
    return trader


def _gen_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _print_source(src: Trader) -> None:
    team = src.team
    teamlead = team.teamlead if team else None
    print("=== Source trader ===")
    print(f"  username : {src.user.username}")
    print(f"  telegram : {src.telegram}")
    print(f"  is_boss  : {src.is_boss}")
    print(f"  boss     : {src.boss.user.username if src.boss else None}")
    print(f"  team     : {team.name if team else None}")
    print(f"  teamlead : {teamlead.user.username if teamlead else None}")
    print(f"  team %   : {team.teamlead_percentage if team else None}")
    print(f"  currency : {src.currency.symbol if src.currency else None}")
    print(f"  language : {src.language.name if src.language else None}")
    print(f"  rate_in  : {team.rate_in if team else None}")
    print(f"  rate_out : {team.rate_out if team else None}")
    if src.balance_usdt_id:
        addrs = list(Address.objects.filter(balance=src.balance_usdt).values_list("address_public", flat=True))
        print(f"  wallets  : {addrs or '—'}")


def run(
    source_lookup: str = SOURCE_LOOKUP,
    target_username: str = TARGET_USERNAME,
    target_telegram: str = TARGET_TELEGRAM,
    deposit_address: str = DEPOSIT_ADDRESS,
) -> Trader:
    src = _find_source(source_lookup)
    _print_source(src)

    if not src.team_id:
        raise SystemExit("Source trader has no team — cannot copy teamlead binding.")
    if not src.currency_id:
        raise SystemExit("Source trader has no currency.")

    target_username = target_username.lstrip("@").strip().lower()
    target_telegram = target_telegram.lstrip("@").strip()
    deposit_address = deposit_address.strip()

    if User.objects.filter(username__iexact=target_username).exists():
        raise SystemExit(f"User '{target_username}' already exists.")
    if Trader.objects.filter(telegram__iexact=target_telegram).exists():
        raise SystemExit(f"Trader with telegram '{target_telegram}' already exists.")
    if Address.objects.filter(address_public=deposit_address).exists():
        raise SystemExit(f"Deposit address already linked: {deposit_address}")

    password = _gen_password()
    sms_username = f"sms{target_username}"
    sms_password = password + "sms"

    with transaction.atomic():
        user = User.objects.create_user(
            username=target_username,
            email=f"{target_username}@example.com",
            password=password,
            first_name=src.user.first_name or target_username,
            is_active=True,
        )
        sms_user = User.objects.create_user(
            username=sms_username,
            email=f"sms{target_username}@example.com",
            password=sms_password,
            first_name=user.first_name,
            is_active=True,
        )

        balance = Balance.objects.create(type=0, amount=Decimal("0"))
        frozen = Balance.objects.create(type=1, amount=Decimal("0"))

        # Отдельный кошелёк пополнения → всегда boss в той же команде (тот же тимлид).
        trader = Trader.objects.create(
            user=user,
            language=src.language,
            telegram=target_telegram,
            phone=src.phone,
            boss=None,
            is_boss=True,
            team=src.team,
            balance_usdt=balance,
            frozen_balance_usdt=frozen,
            currency=src.currency,
            blocked=False,
            super_blocked=False,
        )
        Address.objects.create(address_public=deposit_address, balance=balance)
        TraderDevice.objects.create(user=sms_user, trader=trader)
        Token.objects.create(user=sms_user)

    team = trader.team
    teamlead = team.teamlead if team else None
    print("\n=== Created trader ===")
    print(f"  username        : {trader.user.username}")
    print(f"  telegram        : @{trader.telegram}")
    print(f"  password        : {password}")
    print(f"  sms_user        : {sms_username}")
    print(f"  sms_password    : {sms_password}")
    print(f"  is_boss         : {trader.is_boss}")
    print(f"  team            : {team.name if team else None}")
    print(f"  teamlead        : {teamlead.user.username if teamlead else None}")
    print(f"  deposit_address : {deposit_address}")
    print("\nNote: for automatic crypto sweep this address must also exist in")
    print("cryptodb.wallets with its private key. Django Address alone links")
    print("credits when /deposits/ returns this address.")
    return trader


if __name__ == "__main__":
    run()
else:
    print("Loaded. Call run() to clone resdfe → resdfe1 with wallet", DEPOSIT_ADDRESS)
