"""
Тест lunatrixpay → C2CKZTTEST → Plutus (plutus1).

Создаёт/обновляет:
  - PaymentSystem C2CKZTTEST (KZT)
  - виртуальную группу у plutus1
  - MerchantSolution у lunatrixpay
  - отключает другие активные группы на C2CKZTTEST (kzt_c2c_test, botonpay1, …)

Перед первым запуском:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_plutus_trader.py

В .env:
  PLUTUS_API_KEY=...
  PLUTUS_TRADER_USERNAME=plutus1
  PUBLIC_API_URL=https://api.avapay.net

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_lunatrix_plutus_c2ckzttest_routing.py

Проверка:
  docker compose exec -T app python manage.py diagnose_routing lunatrixpay --ps C2CKZTTEST --amount 100 --ftd false

Создать сделку:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_lunatrix_plutus_c2ckzttest_payin.py
"""
from __future__ import annotations

import os

from basics.shell_setup_plutus_c2ckzttest_routing import (
    PS_NAME,
    TRAFFIC_NAME,
    TEAM_NAME,
    ensure_merchant_solution,
    ensure_payment_system,
    ensure_plutus_virtual_group,
)
from basics.models import Currency, Trader, TraderTeam, TraderTeamRates, TrafficType
from django.contrib.auth.models import User
from django.db import transaction
from decimal import Decimal

from merchant.models import Merchant
from payments.plutus_client import plutus_trader_username

MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "lunatrixpay").strip()


def deactivate_other_groups(ps, *, keep_username: str) -> None:
    keep_trader = Trader.objects.filter(user__username=keep_username).first()
    from basics.models import PaymentDetailsGroup

    qs = PaymentDetailsGroup.objects.filter(payment_system=ps, in_active=True).select_related("trader__user")
    if keep_trader:
        qs = qs.exclude(trader_id=keep_trader.id)
    for group in qs:
        uname = group.trader.user.username if group.trader and group.trader.user else "?"
        group.in_active = False
        group.save(update_fields=["in_active"])
        print(f"  - deactivated group {group.id} trader={uname}")


@transaction.atomic
def run() -> None:
    print("=" * 60)
    print(f"Lunatrix → Plutus routing: {MERCHANT_USERNAME} → {PS_NAME} → {plutus_trader_username()}")
    print("=" * 60)

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        raise RuntimeError("Currency KZT not found")

    ps = ensure_payment_system(kzt)
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    trader_user = User.objects.filter(username=plutus_trader_username()).first()
    if trader_user is None:
        raise RuntimeError(
            f"Trader {plutus_trader_username()!r} not found — run shell_create_plutus_trader.py"
        )
    trader = Trader.objects.filter(user=trader_user).select_related("team").first()
    if trader is None:
        raise RuntimeError(f"Trader profile {plutus_trader_username()!r} not found")

    team = trader.team
    if team is None:
        from basics.models import TraderTeam

        team = TraderTeam.objects.filter(name=TEAM_NAME).first()
    if team is None:
        raise RuntimeError(f"Team {TEAM_NAME!r} not found")
    TraderTeamRates.objects.get_or_create(
        team=team,
        payment_system=ps,
        defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")},
    )

    if trader.balance_usdt.amount < Decimal("1000"):
        trader.balance_usdt.amount = Decimal("50000")
        trader.balance_usdt.save(update_fields=["amount"])
        print(f"  + topped balance_usdt for {plutus_trader_username()}")

    ensure_plutus_virtual_group(trader, ps, kzt, traffic)
    deactivate_other_groups(ps, keep_username=plutus_trader_username())

    merchant = Merchant.objects.filter(user__username=MERCHANT_USERNAME).first()
    if merchant is None:
        raise RuntimeError(f"Merchant {MERCHANT_USERNAME!r} not found")
    ensure_merchant_solution(merchant, ps, traffic)

    print("")
    print("Done.")
    print(f"  • Pay-in: merchant={MERCHANT_USERNAME}, payment_system={PS_NAME}, currency=KZT")
    print(
        f"  • diagnose: python manage.py diagnose_routing {MERCHANT_USERNAME} "
        f"--ps {PS_NAME} --amount 100 --ftd false"
    )
    print("  • create: shell_create_lunatrix_plutus_c2ckzttest_payin.py")
    print("  • sandbox Plutus: сумма 100 → автоколбек ~5 с (если PLUTUS_API_KEY=th_sandbox_...)")


run()
