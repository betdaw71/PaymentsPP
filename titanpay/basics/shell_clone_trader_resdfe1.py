"""
Создание новой команды + трейдера resdfe1 по образцу resdfe:
- новая TraderTeam с тем же тимлидом и теми же ставками
- копия TraderTeamRates по платёжным системам
- трейдер-босс с кастомным TRC20-кошельком пополнения

Запуск на сервере:
  docker compose exec -T app python manage.py shell < basics/shell_clone_trader_resdfe1.py
"""
from __future__ import annotations

import secrets
import string
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.authtoken.models import Token

from basics.models import Balance, Trader, TraderTeam, TraderTeamRates
from sms.models import TraderDevice
from trade.models import Address

SOURCE_LOOKUP = "resdfe"
TARGET_USERNAME = "resdfe1"
TARGET_TELEGRAM = "resdfe1"
NEW_TEAM_NAME = "resdfe1"
DEPOSIT_ADDRESS = "TJtxY4nnixqBGMf1PMqFokH8HirHxH7eXC"


def _find_source(lookup: str) -> Trader:
    clean = lookup.lstrip("@").strip()
    qs = Trader.objects.select_related(
        "user", "team", "team__teamlead", "team__teamlead__user",
        "language", "currency", "boss", "boss__user", "balance_usdt",
    )
    trader = qs.filter(user__username__iexact=clean).first()
    if trader is None:
        trader = qs.filter(telegram__iexact=clean).first()
    if trader is None:
        trader = qs.filter(telegram__iexact=f"@{clean}").first()
    if trader is None:
        raise SystemExit(f"Source trader '{lookup}' not found (username/telegram).")
    return trader


def _gen_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _print_source(src: Trader) -> None:
    team = src.team
    teamlead = team.teamlead if team else None
    rates = list(
        TraderTeamRates.objects.filter(team=team).select_related("payment_system")
    ) if team else []
    print("=== Source trader ===")
    print(f"  username : {src.user.username}")
    print(f"  telegram : {src.telegram}")
    print(f"  is_boss  : {src.is_boss}")
    print(f"  team     : {team.name if team else None}")
    print(f"  teamlead : {teamlead.user.username if teamlead else None}")
    print(f"  team %   : {team.teamlead_percentage if team else None}")
    print(f"  rate_in  : {team.rate_in if team else None}")
    print(f"  rate_out : {team.rate_out if team else None}")
    print(f"  currency : {src.currency.symbol if src.currency else None}")
    print(f"  language : {src.language.name if src.language else None}")
    if rates:
        print("  MDR rates:")
        for r in rates:
            print(f"    - {r.payment_system.name}: in={r.mdr_in}% out={r.mdr_out}%")
    if src.balance_usdt_id:
        addrs = list(Address.objects.filter(balance=src.balance_usdt).values_list("address_public", flat=True))
        print(f"  wallets  : {addrs or '—'}")


def run(
    source_lookup: str = SOURCE_LOOKUP,
    target_username: str = TARGET_USERNAME,
    target_telegram: str = TARGET_TELEGRAM,
    new_team_name: str = NEW_TEAM_NAME,
    deposit_address: str = DEPOSIT_ADDRESS,
) -> Trader:
    src = _find_source(source_lookup)
    _print_source(src)

    if not src.team_id:
        raise SystemExit("Source trader has no team — cannot copy settings/teamlead.")
    if not src.currency_id:
        raise SystemExit("Source trader has no currency.")

    src_team = src.team
    target_username = target_username.lstrip("@").strip().lower()
    target_telegram = target_telegram.lstrip("@").strip()
    new_team_name = new_team_name.strip()
    deposit_address = deposit_address.strip()

    if User.objects.filter(username__iexact=target_username).exists():
        raise SystemExit(f"User '{target_username}' already exists.")
    if Trader.objects.filter(telegram__iexact=target_telegram).exists():
        raise SystemExit(f"Trader with telegram '{target_telegram}' already exists.")
    if TraderTeam.objects.filter(name=new_team_name).exists():
        raise SystemExit(f"Team '{new_team_name}' already exists.")
    if Address.objects.filter(address_public=deposit_address).exists():
        raise SystemExit(f"Deposit address already linked: {deposit_address}")

    password = _gen_password()
    sms_username = f"sms{target_username}"
    sms_password = password + "sms"
    src_rates = list(TraderTeamRates.objects.filter(team=src_team).select_related("payment_system"))

    with transaction.atomic():
        # Новая команда: тот же тимлид и ставки, страховой депозит с нуля.
        team = TraderTeam.objects.create(
            name=new_team_name,
            rate_in=src_team.rate_in,
            rate_out=src_team.rate_out,
            teamlead=src_team.teamlead,
            teamlead_percentage=src_team.teamlead_percentage,
            insurance_deposit=Decimal("0"),
        )
        for r in src_rates:
            TraderTeamRates.objects.create(
                team=team,
                payment_system=r.payment_system,
                mdr_in=r.mdr_in,
                mdr_out=r.mdr_out,
            )

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

        trader = Trader.objects.create(
            user=user,
            language=src.language,
            telegram=target_telegram,
            phone=src.phone,
            boss=None,
            is_boss=True,
            team=team,
            balance_usdt=balance,
            frozen_balance_usdt=frozen,
            currency=src.currency,
            blocked=False,
            super_blocked=False,
        )
        Address.objects.create(address_public=deposit_address, balance=balance)
        TraderDevice.objects.create(user=sms_user, trader=trader)
        Token.objects.create(user=sms_user)

    teamlead = team.teamlead
    print("\n=== Created NEW team + trader ===")
    print(f"  team            : {team.name} ({team.id})")
    print(f"  teamlead        : {teamlead.user.username if teamlead else None}")
    print(f"  teamlead %      : {team.teamlead_percentage}")
    print(f"  rate_in/out     : {team.rate_in}% / {team.rate_out}%")
    print(f"  MDR copied      : {len(src_rates)} payment system(s)")
    print(f"  insurance       : ${team.insurance_deposit} (fresh team)")
    print(f"  username        : {trader.user.username}")
    print(f"  telegram        : @{trader.telegram}")
    print(f"  password        : {password}")
    print(f"  sms_user        : {sms_username}")
    print(f"  sms_password    : {sms_password}")
    print(f"  is_boss         : {trader.is_boss}")
    print(f"  deposit_address : {deposit_address}")
    print("\nNext:")
    print("  1) Head support: add team to controlled_teams if needed")
    print("  2) For auto crypto sweep: add address+private_key to cryptodb.wallets")
    return trader


if __name__ == "__main__":
    run()
else:
    print(
        "Loaded. Call run() to create NEW team + trader resdfe1 "
        f"with wallet {DEPOSIT_ADDRESS}"
    )
