"""
Prod: активировать PayPlat (payplat1) на C2CKZT и C2C (KZT), отключить тест C2CKZTTEST.

Также снимает arbitrage-block (status=4) с групп payplat1, если они были заблокированы ранее.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_payplat_ensure_prod_groups.py

Проверка:
  docker compose exec -T app python manage.py diagnose_routing pandapay --ps C2CKZT --amount 10000 --ftd false
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from basics.models import (
    Currency,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeamRates,
    TrafficType,
)
from payments.payplat_client import payplat_trader_username
from titanpay.settings import C2C_NAME

GROUP_OWNER = "PayPlat Virtual Drop"
TRAFFIC_NAME = "Standard"
PROD_PS_NAMES = ("C2CKZT", C2C_NAME)
TEST_PS_NAME = "C2CKZTTEST"
CURRENCY_SYMBOL = "KZT"
DEFAULT_MDR_IN = Decimal("7")
PSP_FLOAT_USDT = Decimal("50000")


def _ensure_virtual_card(group: PaymentDetailsGroup) -> None:
    cards = PaymentDetails.objects.filter(
        group=group,
        status=1,
        sberpay_enabled=False,
        sbp_enabled=False,
        card_number__isnull=False,
    ).count()
    if cards:
        return
    card = "4" + uuid.uuid4().hex[:15]
    card = "".join(c for c in card if c.isdigit())[:16].ljust(16, "0")
    PaymentDetails.objects.create(
        group=group,
        status=1,
        amount=Decimal("999999"),
        card_number=card,
        deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
        sberpay_enabled=False,
        sbp_enabled=False,
    )
    print(f"    + virtual card for group {group.id}")


def ensure_group(trader: Trader, kzt: Currency, ps: PaymentSystem, traffic: TrafficType) -> PaymentDetailsGroup:
    group = PaymentDetailsGroup.objects.filter(
        trader=trader,
        payment_system=ps,
        currency=kzt,
    ).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner=f"{GROUP_OWNER} {ps.name}",
            trader=trader,
            currency=kzt,
            payment_system=ps,
            status=1,
            amount=Decimal("999999"),
            in_active=True,
            out_active=False,
            min_amount_out=Decimal("1000"),
            max_amount_out=Decimal("5000000"),
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
            current_volume=Decimal("0"),
        )
        group.allowed_traffic.add(traffic)
        print(f"  + group {ps.name} ({group.id})")
    else:
        changed = False
        for field, val in (
            ("status", 1),
            ("in_active", True),
            ("amount", Decimal("999999")),
        ):
            if getattr(group, field) != val:
                setattr(group, field, val)
                changed = True
        if changed:
            group.save()
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ group {ps.name} ({group.id}) status={group.status} in_active={group.in_active}")
    _ensure_virtual_card(group)
    return group


def deactivate_test_ps(trader: Trader, kzt: Currency) -> None:
    test_ps = PaymentSystem.objects.filter(name=TEST_PS_NAME, currency=kzt).first()
    if test_ps is None:
        return
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=test_ps, currency=kzt).first()
    if group is None:
        return
    if group.in_active:
        group.in_active = False
        group.save(update_fields=["in_active"])
        print(f"  - deactivated test PS {TEST_PS_NAME} group {group.id}")


def unblock_arbitrage_groups(trader: Trader) -> None:
    updated = PaymentDetailsGroup.objects.filter(trader=trader, status=4).update(status=1)
    if updated:
        print(f"  + unblocked {updated} group(s) from arbitrage status=4 → 1")


def run() -> None:
    username = payplat_trader_username()
    print(f"=== PayPlat ensure prod groups ({username}) ===")

    user = User.objects.filter(username=username).first()
    if user is None:
        print(f"ERROR: user {username!r} not found — run shell_create_payplat_trader.py")
        return
    trader = Trader.objects.filter(user=user).select_related("team").first()
    if trader is None:
        print(f"ERROR: trader {username!r} not found")
        return

    kzt = Currency.objects.filter(symbol=CURRENCY_SYMBOL).first()
    if kzt is None:
        print(f"ERROR: currency {CURRENCY_SYMBOL} not found")
        return

    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    unblock_arbitrage_groups(trader)

    for ps_name in PROD_PS_NAMES:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
        if ps is None:
            print(f"  WARN: PaymentSystem {ps_name}+KZT not found — skip")
            continue
        if trader.team_id:
            TraderTeamRates.objects.get_or_create(
                team=trader.team,
                payment_system=ps,
                defaults={"mdr_in": DEFAULT_MDR_IN, "mdr_out": Decimal("2.5")},
            )
        ensure_group(trader, kzt, ps, traffic)

    deactivate_test_ps(trader, kzt)

    if trader.balance_usdt.amount < PSP_FLOAT_USDT:
        trader.balance_usdt.amount = PSP_FLOAT_USDT
        trader.balance_usdt.save(update_fields=["amount"])
        print(f"  + topped balance_usdt to {PSP_FLOAT_USDT} for {username}")

    print("")
    print("Groups on trader:")
    for g in PaymentDetailsGroup.objects.filter(trader=trader).select_related("payment_system"):
        cards = PaymentDetails.objects.filter(group=g, status=1).count()
        print(
            f"  PS={g.payment_system.name} id={g.id} in_active={g.in_active} "
            f"status={g.status} cards={cards}"
        )

    print("")
    print(".env prod:")
    print("  PAYPLAT_API_BASE=https://payplat.su/v1/api")
    print("  PAYPLAT_REQUISITE_TYPE_MAP={\"C2C\":\"c2c_ab\",\"C2CKZT\":\"c2c_ab\"}")
    print("  PAYPLAT_PAYER_MAP={\"C2C\":\"kz\",\"C2CKZT\":\"kz\"}")
    print("  shell_setup_payplat_appeal.py — апелляционный бот")
    print("  ARBITRAGE_BLOCK_PAYMENT_GROUP=false")
    print("")
    print("Check routing:")
    print("  python manage.py diagnose_routing pandapay --ps C2CKZT --amount 10000 --ftd false")


run()
