"""
Prod pandapay KZT: gipay1 + payplat1 активны и первые в каскаде на C2CKZT/C2C.

Другие PSP не отключаются — только низкий mdr_in у payplat/gipay (раньше в каскаде).
Проблема «нет сессии GiPay/PayPlat» = группа in_active=False или нет виртуальной карты.

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
from payments.psp_payin import psp_trader_usernames, sort_groups_for_routing
from titanpay.settings import C2C_NAME

MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "pandapay").strip()
TRAFFIC_NAME = "Standard"
PROD_PS_NAMES = ("C2CKZT", C2C_NAME)

# mdr_in: меньше = раньше в каскаде (остальные PSP не трогаем)
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


def topup_psp_float(trader: Trader, username: str) -> None:
    if trader is None:
        print(f"  ! trader {username!r} not found")
        return
    target = PSP_FLOAT_USDT if username == payplat_trader_username() else Decimal("50000")
    if trader.balance_usdt.amount < target:
        trader.balance_usdt.amount = target
        trader.balance_usdt.save(update_fields=["amount"])
        print(f"  + topped balance_usdt to {target} for {username}")


def print_cascade_preview(kzt: Currency, traffic: TrafficType) -> None:
    ps = PaymentSystem.objects.filter(name="C2CKZT", currency=kzt).first()
    if ps is None:
        return
    groups = list(
        PaymentDetailsGroup.objects.filter(
            payment_system=ps,
            status=1,
            in_active=True,
            work_type="by_card",
            allowed_traffic=traffic,
            trader__blocked=False,
            trader__user__username__in=psp_trader_usernames(),
        ).select_related("trader", "trader__user", "trader__team")
    )
    print("\nКаскад PSP на C2CKZT (первые 8):")
    for i, g in enumerate(sort_groups_for_routing(groups)[:8], 1):
        uname = g.trader.user.username if g.trader and g.trader.user else "?"
        print(f"  {i}. {uname}")


@transaction.atomic
def run() -> None:
    print("=" * 60)
    print(f"Prod routing: {MERCHANT_USERNAME} — payplat1 + gipay1 в топе каскада")
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

    set_mdr(payplat, kzt, MDR_BY_TRADER[payplat_trader_username()])
    set_mdr(gipay, kzt, MDR_BY_TRADER[gipay_trader_username()])
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

    print_cascade_preview(kzt, traffic)
    print("\nDone. payplat1 и gipay1 активны; остальные PSP не отключались.")
    print("  diagnose_routing pandapay --ps C2CKZT --amount 7010 --ftd false")


run()
