"""
Prod pandapay KZT: gipay1 + payplat1 активны и первые в каскаде на C2CKZT/C2C.

Не меняет TraderTeamRates.mdr_in и balance_usdt (учёт балансов не трогаем).
Не перезаписывает лимиты существующих MerchantSolution.
Приоритет каскада — через .env PSP_ROUTING_PRIORITY_MAP (см. settings.py).

Безопасно перезапускать после сбоя: только включает prod-группы и выключает C2CKZTTEST.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_pandapay_gipay_payplat_prod_routing.py

.env (приоритет, меньше = раньше):
  PSP_ROUTING_PRIORITY_MAP={"payplat1": 1, "gipay1": 2}

Проверка:
  docker compose exec -T app python manage.py diagnose_routing pandapay --ps C2CKZT --amount 7010 --ftd false
"""
from __future__ import annotations

import os

from django.contrib.auth.models import User

from basics.models import Currency, PaymentDetailsGroup, PaymentSystem, Trader, TrafficType
from basics.shell_gipay_ensure_prod_groups import ensure_group as ensure_gipay_group
from basics.shell_payplat_ensure_prod_groups import (
    deactivate_test_ps,
    ensure_group as ensure_payplat_group,
    unblock_arbitrage_groups,
)
from basics.shell_merchant_solution import ensure_merchant_solution
from merchant.models import Merchant
from payments.gipay_client import gipay_trader_username
from payments.payplat_client import payplat_trader_username
from payments.psp_payin import (
    psp_routing_priority_for_trader,
    psp_trader_usernames,
    sort_groups_for_routing,
)
from titanpay.settings import C2C_NAME

MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "pandapay").strip()
TRAFFIC_NAME = "Standard"
PROD_PS_NAMES = ("C2CKZT", C2C_NAME)


def _trader(username: str) -> Trader | None:
    user = User.objects.filter(username=username).first()
    if user is None:
        return None
    return Trader.objects.filter(user=user).select_related("team").first()


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
    print("\nКаскад PSP на C2CKZT (первые 8; priority из PSP_ROUTING_PRIORITY_MAP):")
    for i, g in enumerate(sort_groups_for_routing(groups)[:8], 1):
        uname = g.trader.user.username if g.trader and g.trader.user else "?"
        prio = psp_routing_priority_for_trader(g.trader)
        print(f"  {i}. {uname}  cascade_priority={prio}")


def run() -> None:
    print("=" * 60)
    print(f"Prod routing: {MERCHANT_USERNAME} — payplat1 + gipay1 активны")
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

    deactivate_test_ps(payplat, kzt)

    for trader in (gipay, payplat):
        uname = trader.user.username if trader.user else "?"
        bal = trader.balance_usdt.amount if trader.balance_usdt else None
        frozen = trader.frozen_balance_usdt.amount if trader.frozen_balance_usdt else None
        print(f"  balance {uname}: available={bal} frozen={frozen} (не меняли)")

    merchant = Merchant.objects.filter(user__username=MERCHANT_USERNAME).first()
    if merchant:
        for ps_name in PROD_PS_NAMES:
            ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
            if ps:
                ensure_merchant_solution(merchant, ps, traffic, overwrite_limits=False)
        print(f"  ✓ merchant {MERCHANT_USERNAME}")
    else:
        print(f"  ! merchant {MERCHANT_USERNAME!r} not found")

    print_cascade_preview(kzt, traffic)
    print("\nDone. mdr_in и balance_usdt не изменялись.")
    print("  Приоритет каскада: PSP_ROUTING_PRIORITY_MAP в .env")
    print('  {"payplat1": 1, "gipay1": 2}')
    print("  diagnose_routing pandapay --ps C2CKZT --amount 7010 --ftd false")


run()
