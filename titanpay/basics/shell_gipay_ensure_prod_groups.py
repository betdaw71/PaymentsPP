"""
Prod: у gipay1 должны быть ОБЕ виртуальные группы — C2CKZT и C2C (KZT), method GiPay = tgkz.

Если C2C работает, а C2CKZT нет — чаще всего нет/выключена группа C2CKZT у gipay1.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_gipay_ensure_prod_groups.py
"""
from __future__ import annotations

import datetime
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
from payments.gipay_client import gipay_trader_username
from titanpay.settings import C2C_NAME

GROUP_OWNER = "GiPay Virtual Drop"
TRAFFIC_NAME = "Standard"
PS_NAMES = ("C2CKZT", C2C_NAME)
CURRENCY_SYMBOL = "KZT"
DEFAULT_MDR_IN = Decimal("7")


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
        )
        group.allowed_traffic.add(traffic)
        print(f"  + group {ps.name} ({group.id})")
    else:
        changed = False
        if group.status != 1:
            group.status = 1
            changed = True
        if not group.in_active:
            group.in_active = True
            changed = True
        if group.amount < Decimal("999999"):
            group.amount = Decimal("999999")
            changed = True
        if changed:
            group.save()
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ group {ps.name} ({group.id}) status={group.status} in_active={group.in_active}")
    _ensure_virtual_card(group)
    return group


def run() -> None:
    username = gipay_trader_username()
    print(f"=== GiPay ensure prod groups ({username}) ===")

    user = User.objects.filter(username=username).first()
    if user is None:
        print(f"ERROR: user {username!r} not found — run shell_create_gipay_trader.py")
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

    for ps_name in PS_NAMES:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
        if ps is None:
            print(f"  WARN: PaymentSystem {ps_name}+KZT not found — skip (run shell_create_gipay_trader / shell_gipay_add_c2c_group)")
            continue
        if trader.team_id:
            TraderTeamRates.objects.get_or_create(
                team=trader.team,
                payment_system=ps,
                defaults={"mdr_in": DEFAULT_MDR_IN, "mdr_out": Decimal("2.5")},
            )
        ensure_group(trader, kzt, ps, traffic)

    print("")
    print("Groups on trader:")
    for g in PaymentDetailsGroup.objects.filter(trader=trader).select_related("payment_system"):
        cards = PaymentDetails.objects.filter(group=g, status=1).count()
        print(
            f"  PS={g.payment_system.name} id={g.id} in_active={g.in_active} "
            f"status={g.status} cards={cards}"
        )

    print("")
    print("Check routing:")
    print("  python manage.py diagnose_routing pandapay --ps C2CKZT --amount 10000 --ftd false")
    print("  python manage.py diagnose_routing pandapay --ps C2C --amount 10000 --ftd false")
    print("")
    print(".env: GIPAY_PAYIN_METHOD=tgkz  (оба PS → tgkz у GiPay API)")


run()
