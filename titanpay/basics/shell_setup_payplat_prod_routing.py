"""
Prod: C2CKZT / C2C → только payplat1 (заявки сразу идут в PayPlat API).

  - активирует группы payplat1 на C2CKZT и C2C
  - отключает C2CKZTTEST у payplat1
  - приоритет каскада через PSP_ROUTING_PRIORITY_MAP в .env (не меняет mdr_in)
  - отключает другие PSP-трейдеры на C2CKZT и C2C
  - снимает arbitrage-block (status=4)

Перед запуском в .env:
  PAYPLAT_API_BASE=https://payplat.su/v1/api
  PAYPLAT_REQUISITE_TYPE_MAP={"C2C":"h2h","C2CKZT":"h2h"}
  PAYPLAT_PAYER_MAP={"C2C":"kz","C2CKZT":"kz"}

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_payplat_prod_routing.py

Опционально — мерчанты:
  MERCHANT_USERNAMES=pandapay docker compose exec -T -e MERCHANT_USERNAMES=pandapay app \\
    python manage.py shell < titanpay/basics/shell_setup_payplat_prod_routing.py

Проверка:
  docker compose exec -T app python manage.py diagnose_routing pandapay --ps C2CKZT --amount 5000 --ftd false
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from basics.models import Currency, PaymentDetailsGroup, PaymentSystem, Trader, TrafficType
from basics.shell_payplat_ensure_prod_groups import (
    CURRENCY_SYMBOL,
    PROD_PS_NAMES,
    PSP_FLOAT_USDT,
    TEST_PS_NAME,
    deactivate_test_ps,
    ensure_group,
    unblock_arbitrage_groups,
)
from basics.shell_setup_payplat_c2ckzttest_routing import ensure_merchant_solution
from merchant.models import Merchant
from payments.payplat_client import payplat_trader_username
from payments.psp_payin import psp_trader_usernames

TRAFFIC_NAME = "Standard"
DEFAULT_MERCHANTS = os.environ.get("MERCHANT_USERNAMES", "pandapay").strip()


def _merchant_usernames() -> list[str]:
    return [u.strip() for u in DEFAULT_MERCHANTS.split(",") if u.strip()]


def deactivate_other_psp_on_prod_ps(kzt: Currency, *, keep_username: str) -> None:
    keep_trader = Trader.objects.filter(user__username=keep_username).first()
    psp_names = psp_trader_usernames()
    for ps_name in PROD_PS_NAMES:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
        if ps is None:
            continue
        qs = PaymentDetailsGroup.objects.filter(payment_system=ps, in_active=True).select_related("trader__user")
        if keep_trader:
            qs = qs.exclude(trader_id=keep_trader.id)
        for group in qs:
            uname = group.trader.user.username if group.trader and group.trader.user else ""
            if uname in psp_names:
                group.in_active = False
                group.save(update_fields=["in_active"])
                print(f"  - deactivated {ps_name} group {group.id} trader={uname}")


def activate_payplat_prod_ps(trader: Trader) -> None:
    for group in PaymentDetailsGroup.objects.filter(trader=trader).select_related("payment_system"):
        ps_name = group.payment_system.name if group.payment_system else ""
        should_active = ps_name in PROD_PS_NAMES
        if ps_name == TEST_PS_NAME:
            should_active = False
        changed = False
        if group.in_active != should_active:
            group.in_active = should_active
            changed = True
        if group.status != 1:
            group.status = 1
            changed = True
        if changed:
            group.save()
            print(f"  ~ payplat1 {ps_name}: in_active={should_active} status=1")


@transaction.atomic
def run() -> None:
    username = payplat_trader_username()
    print("=" * 60)
    print(f"PayPlat PROD routing: {username} primary on {', '.join(PROD_PS_NAMES)}")
    print("=" * 60)

    user = User.objects.filter(username=username).first()
    if user is None:
        raise RuntimeError(f"Trader {username!r} not found — run shell_create_payplat_trader.py first")
    trader = Trader.objects.filter(user=user).select_related("team").first()
    if trader is None:
        raise RuntimeError(f"Trader record missing for {username!r}")

    kzt = Currency.objects.filter(symbol=CURRENCY_SYMBOL).first()
    if kzt is None:
        raise RuntimeError(f"Currency {CURRENCY_SYMBOL} not found")

    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    unblock_arbitrage_groups(trader)
    activate_payplat_prod_ps(trader)

    for ps_name in PROD_PS_NAMES:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
        if ps is None:
            print(f"  WARN: PaymentSystem {ps_name}+KZT not found — skip")
            continue
        ensure_group(trader, kzt, ps, traffic)

    deactivate_test_ps(trader, kzt)
    deactivate_other_psp_on_prod_ps(kzt, keep_username=username)

    if trader.balance_usdt.amount < PSP_FLOAT_USDT:
        trader.balance_usdt.amount = PSP_FLOAT_USDT
        trader.balance_usdt.save(update_fields=["amount"])
        print(f"  + topped balance_usdt to {PSP_FLOAT_USDT} for {username}")

    for merchant_username in _merchant_usernames():
        try:
            merchant = Merchant.objects.get(user__username=merchant_username)
        except Merchant.DoesNotExist:
            print(f"  ! merchant {merchant_username!r} not found — skip")
            continue
        for ps_name in PROD_PS_NAMES:
            ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
            if ps is None:
                continue
            ensure_merchant_solution(merchant, ps, traffic)
        print(f"  ✓ merchant {merchant_username} → {', '.join(PROD_PS_NAMES)}")

    print("\nDone.")
    print(f"  • payplat1 первый в каскаде через PSP_ROUTING_PRIORITY_MAP (mdr_in не менялся)")
    print("  • другие PSP (botonpay, gipay, …) на этих PS отключены")
    print("  • restart app после .env PAYPLAT_*")
    print("  • diagnose_routing pandapay --ps C2CKZT --amount 5000 --ftd false")
    print("  • в логах: payplat_out_request с payer=kz, requisite_type=h2h")


run()
