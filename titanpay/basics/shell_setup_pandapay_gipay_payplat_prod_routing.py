"""
Prod pandapay KZT: gipay1 + payplat1 активны на C2CKZT/C2C, сломанные PSP отключены.

Проблема «нет сессии GiPay/PayPlat» = API не вызывался: группа in_active=False или нет виртуальной карты.
Не связано с балансом USDT и не с «нехваткой виртуальных реквизитов на одинаковые суммы».

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_pandapay_gipay_payplat_prod_routing.py

Проверка:
  docker compose exec -T app python manage.py diagnose_routing pandapay --ps C2CKZT --amount 7010 --ftd false
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from basics.models import Currency, PaymentDetailsGroup, PaymentSystem, Trader, TraderTeamRates, TrafficType
from basics.shell_gipay_ensure_prod_groups import ensure_group as ensure_gipay_group
from basics.shell_payplat_ensure_prod_groups import (
    PSP_FLOAT_USDT,
    ensure_group as ensure_payplat_group,
    unblock_arbitrage_groups,
)
from basics.shell_setup_payplat_c2ckzttest_routing import ensure_merchant_solution
from merchant.models import Merchant
from payments.gipay_client import gipay_trader_username
from payments.payplat_client import payplat_trader_username
from payments.psp_payin import psp_trader_usernames
from titanpay.settings import C2C_NAME

MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "pandapay").strip()
TRAFFIC_NAME = "Standard"
PROD_PS_NAMES = ("C2CKZT", C2C_NAME)

# Рабочие PSP (оставляем в каскаде)
KEEP_ACTIVE = frozenset({gipay_trader_username(), payplat_trader_username()})

# mdr_in: меньше = раньше в каскаде
MDR_BY_TRADER = {
    payplat_trader_username(): Decimal(os.environ.get("PAYPLAT_MDR_IN", "0.3")),
    gipay_trader_username(): Decimal(os.environ.get("GIPAY_MDR_IN", "0.5")),
}


def _trader(username: str) -> Trader | None:
    user = User.objects.filter(username=username).first()
    if user is None:
        return None
    return Trader.objects.filter(user=user).select_related("team").first()


def set_mdr(trader: Trader, kzt: Currency, mdr_in: Decimal) -> None:
    if not trader or not trader.team_id:
        return
    for ps_name in PROD_PS_NAMES:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
        if ps is None:
            continue
        rate, created = TraderTeamRates.objects.get_or_create(
            team=trader.team,
            payment_system=ps,
            defaults={"mdr_in": mdr_in, "mdr_out": Decimal("2.5")},
        )
        if not created and rate.mdr_in != mdr_in:
            rate.mdr_in = mdr_in
            rate.save(update_fields=["mdr_in"])
        print(f"  ~ {trader.user.username} mdr_in={mdr_in}% on {ps_name}")


def deactivate_broken_psp_on_prod(kzt: Currency) -> None:
    psp_names = psp_trader_usernames()
    for ps_name in PROD_PS_NAMES:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
        if ps is None:
            continue
        qs = PaymentDetailsGroup.objects.filter(payment_system=ps, in_active=True).select_related("trader__user")
        for group in qs:
            uname = group.trader.user.username if group.trader and group.trader.user else ""
            if uname in psp_names and uname not in KEEP_ACTIVE:
                group.in_active = False
                group.save(update_fields=["in_active"])
                print(f"  - deactivated {ps_name} group {group.id} trader={uname}")


def topup_psp_float(trader: Trader, username: str) -> None:
    if trader is None:
        print(f"  ! trader {username!r} not found")
        return
    target = PSP_FLOAT_USDT if username == payplat_trader_username() else Decimal("50000")
    if trader.balance_usdt.amount < target:
        trader.balance_usdt.amount = target
        trader.balance_usdt.save(update_fields=["amount"])
        print(f"  + topped balance_usdt to {target} for {username}")


@transaction.atomic
def run() -> None:
    print("=" * 60)
    print(f"Prod routing: {MERCHANT_USERNAME} → gipay1 + payplat1 on {', '.join(PROD_PS_NAMES)}")
    print("=" * 60)

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        raise RuntimeError("Currency KZT not found")

    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    gipay = _trader(gipay_trader_username())
    payplat = _trader(payplat_trader_username())
    if gipay is None:
        raise RuntimeError(f"{gipay_trader_username()!r} not found — run shell_create_gipay_trader.py")
    if payplat is None:
        raise RuntimeError(f"{payplat_trader_username()!r} not found — run shell_create_payplat_trader.py")

    for trader in (gipay, payplat):
        unblock_arbitrage_groups(trader)

    for ps_name in PROD_PS_NAMES:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
        if ps is None:
            print(f"  WARN: PS {ps_name} not found")
            continue
        ensure_gipay_group(gipay, kzt, ps, traffic)
        ensure_payplat_group(payplat, kzt, ps, traffic)

    set_mdr(gipay, kzt, MDR_BY_TRADER[gipay_trader_username()])
    set_mdr(payplat, kzt, MDR_BY_TRADER[payplat_trader_username()])
    deactivate_broken_psp_on_prod(kzt)
    topup_psp_float(gipay, gipay_trader_username())
    topup_psp_float(payplat, payplat_trader_username())

    merchant = Merchant.objects.filter(user__username=MERCHANT_USERNAME).first()
    if merchant:
        for ps_name in PROD_PS_NAMES:
            ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
            if ps:
                ensure_merchant_solution(merchant, ps, traffic)
        print(f"  ✓ merchant {MERCHANT_USERNAME}")
    else:
        print(f"  ! merchant {MERCHANT_USERNAME!r} not found")

    print("\nActive PSP groups on C2CKZT:")
    ps = PaymentSystem.objects.filter(name="C2CKZT", currency=kzt).first()
    if ps:
        for g in PaymentDetailsGroup.objects.filter(payment_system=ps, in_active=True).select_related("trader__user"):
            uname = g.trader.user.username if g.trader and g.trader.user else "?"
            print(f"  • {uname} group={g.id} status={g.status}")

    print("\nDone. Каскад: payplat1 → gipay1 → (остальные PSP отключены на C2CKZT/C2C)")
    print("  diagnose_routing pandapay --ps C2CKZT --amount 7010 --ftd false")


run()
