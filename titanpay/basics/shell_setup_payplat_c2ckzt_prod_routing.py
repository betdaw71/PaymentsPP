"""
Prod PayPlat: C2CKZT → payplat1 (включает prod PS, отключает C2CKZTTEST у payplat1).

Перед запуском в .env:
  PAYPLAT_API_BASE=https://payplat.su/v1/api
  PAYPLAT_SHOP_ID=<prod>
  PAYPLAT_SECRET_KEY=<prod secret>
  PAYPLAT_REQUISITE_TYPE_MAP={"C2C":"h2h","C2CKZT":"h2h","C2CKZTTEST":"h2h"}
  PUBLIC_API_URL=https://api.avapay.net

IPN в ЛК PayPlat:
  https://api.avapay.net/api/v1/webhooks/psp/payplat/

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_payplat_c2ckzt_prod_routing.py

Опционально — мерчанты (через запятую):
  MERCHANT_USERNAMES=pandapay,lunatrixpay docker compose exec -T -e MERCHANT_USERNAMES=pandapay,lunatrixpay app \\
    python manage.py shell < titanpay/basics/shell_setup_payplat_c2ckzt_prod_routing.py

Проверка:
  docker compose exec -T app python manage.py diagnose_routing pandapay --ps C2CKZT --amount 10000 --ftd false
"""
from __future__ import annotations

import os

from basics.shell_setup_payplat_c2ckzttest_routing import (
    LIMITS,
    PSP_FLOAT_USDT,
    TRAFFIC_NAME,
    ensure_merchant_solution,
    ensure_payplat_virtual_group,
    set_payplat_groups_active,
)
from basics.models import Currency, PaymentDetailsGroup, PaymentSystem, Trader, TraderTeam, TraderTeamRates, TrafficType
from django.contrib.auth.models import User
from django.db import transaction
from merchant.models import Merchant
from payments.payplat_client import payplat_trader_username

PS_NAME = "C2CKZT"
TEST_PS_NAME = "C2CKZTTEST"
GROUP_OWNER = "PayPlat Virtual Drop KZT C2CKZT"
TEAM_NAME = "PayPlat Agg"
DEFAULT_MERCHANTS = "lunatrixpay"


def _merchant_usernames() -> list[str]:
    raw = (os.environ.get("MERCHANT_USERNAMES") or DEFAULT_MERCHANTS).strip()
    return [u.strip() for u in raw.split(",") if u.strip()]


@transaction.atomic
def run() -> None:
    print("=" * 60)
    print(f"PayPlat PROD routing: PS={PS_NAME}")
    print("=" * 60)

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        raise RuntimeError("Currency KZT not found")

    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
    if ps is None:
        raise RuntimeError(f"PaymentSystem {PS_NAME} not found — create prod PS first")

    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    trader_user = User.objects.filter(username=payplat_trader_username()).first()
    if trader_user is None:
        raise RuntimeError(
            f"Trader {payplat_trader_username()!r} not found — run shell_create_payplat_trader.py first"
        )
    trader = Trader.objects.filter(user=trader_user).first()
    if trader is None:
        raise RuntimeError(f"Trader record missing for {payplat_trader_username()!r}")

    team = TraderTeam.objects.filter(name=TEAM_NAME).first()
    if team and trader.team_id != team.id:
        trader.team = team
        trader.save(update_fields=["team"])

    TraderTeamRates.objects.get_or_create(
        team=trader.team,
        payment_system=ps,
        defaults={"mdr_in": 7, "mdr_out": 2.5},
    )

    # Переиспользуем helper, owner подменим на prod-лейбл
    group = ensure_payplat_virtual_group(trader, ps, kzt, traffic)
    if group.owner != GROUP_OWNER:
        group.owner = GROUP_OWNER
        group.save(update_fields=["owner"])

    set_payplat_groups_active(trader=trader, active_ps_name=PS_NAME)

    test_ps = PaymentSystem.objects.filter(name=TEST_PS_NAME, currency=kzt).first()
    if test_ps:
        test_group = trader.payment_details_groups.filter(payment_system=test_ps).first()
        if test_group and test_group.in_active:
            test_group.in_active = False
            test_group.save(update_fields=["in_active"])
            print(f"  ~ payplat1 {TEST_PS_NAME}: in_active=False")

    if trader.balance_usdt.amount < PSP_FLOAT_USDT:
        trader.balance_usdt.amount = PSP_FLOAT_USDT
        trader.balance_usdt.save(update_fields=["amount"])
        print(f"  + topped balance_usdt to {PSP_FLOAT_USDT} for {payplat_trader_username()}")

    unblocked = PaymentDetailsGroup.objects.filter(
        trader=trader,
        status=4,
    ).update(status=1)
    if unblocked:
        print(f"  + unblocked {unblocked} payplat group(s) from arbitrage status=4 → 1")

    for merchant_username in _merchant_usernames():
        try:
            merchant = Merchant.objects.get(user__username=merchant_username)
        except Merchant.DoesNotExist:
            print(f"  ! merchant {merchant_username!r} not found — skip")
            continue
        ensure_merchant_solution(merchant, ps, traffic)
        print(f"  ✓ merchant {merchant_username} → {PS_NAME}")

    print("\nDone.")
    print(f"  • payplat1: active on {PS_NAME}, test PS {TEST_PS_NAME} off")
    print(f"  • other PSP on {PS_NAME} not touched (routing by mdr/volume)")
    print("  • restart app after .env PAYPLAT_* prod keys")
    print(f"  • diagnose: diagnose_routing <merchant> --ps {PS_NAME} --amount 10000 --ftd false")


run()
