"""
Тест апелляций: lunatrixpay → C2CKZTTEST → локальный трейдер kzt_c2c_test.

Создаёт/обновляет:
  - PaymentSystem C2CKZTTEST (KZT), если нет
  - виртуальную группу + реквизит у kzt_c2c_test
  - MerchantSolution у lunatrixpay
  - отключает активные C2CKZTTEST-группы у PSP-трейдеров (botonpay1, plutus1, …)

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_lunatrix_kzt_c2ckzttest_appeal.py

Проверка роутинга:
  docker compose exec -T app python manage.py diagnose_routing lunatrixpay --ps C2CKZTTEST --amount 10000 --ftd false

Pay-in: payment_system=C2CKZTTEST, currency=KZT, merchant=lunatrixpay
"""
from __future__ import annotations

import datetime
import os
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
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
from merchant.models import Merchant, MerchantSolution

PS_NAME = os.environ.get("TEST_PS_NAME", "C2CKZTTEST").strip()
MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "lunatrixpay").strip()
TRADER_USERNAME = os.environ.get("TRADER_USERNAME", "kzt_c2c_test").strip()
TRAFFIC_NAME = "Standard"
GROUP_OWNER = f"Lunatrix KZT appeal test ({TRADER_USERNAME})"
LIMITS = {
    "min_limit_in": Decimal(os.environ.get("TEST_MIN_IN", "1000")),
    "max_limit_in": Decimal(os.environ.get("TEST_MAX_IN", "500000")),
    "min_limit_out": Decimal("1000"),
    "max_limit_out": Decimal("500000"),
}


def _virtual_card() -> str:
    card = "4" + uuid.uuid4().hex[:15]
    return "".join(c for c in card if c.isdigit())[:16].ljust(16, "0")


def ensure_payment_system(kzt: Currency) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
    if ps:
        if not ps.in_on:
            ps.in_on = True
            ps.save(update_fields=["in_on"])
        print(f"  ~ PaymentSystem {ps.name} ({ps.id})")
        return ps
    ps = PaymentSystem.objects.create(
        name=PS_NAME,
        currency=kzt,
        usdt_exchange_rate=Decimal("520"),
        expired_time_in=datetime.timedelta(minutes=15),
        expired_time_out=datetime.timedelta(minutes=10),
        confirm_time_out=datetime.timedelta(minutes=10),
        constrain_time_out=datetime.timedelta(hours=4),
        in_on=True,
        out_on=False,
        sbp_compatible=False,
        required_fields={
            "card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"},
            "owner": {"regex": r"^.+$", "pattern": "Card holder"},
            "bank": {"regex": r"^.+$", "pattern": "Bank"},
        },
    )
    print(f"  + PaymentSystem {ps.name} ({ps.id})")
    return ps


def ensure_trader_group(trader: Trader, ps: PaymentSystem, kzt: Currency, traffic: TrafficType) -> PaymentDetailsGroup:
    group = PaymentDetailsGroup.objects.filter(
        trader=trader,
        payment_system=ps,
        currency=kzt,
    ).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner=GROUP_OWNER,
            trader=trader,
            currency=kzt,
            payment_system=ps,
            status=1,
            amount=Decimal("9999999"),
            in_active=True,
            out_active=False,
            min_amount_out=Decimal("1000"),
            max_amount_out=Decimal("5000000"),
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
            current_volume=Decimal("0"),
            current_out_volume=Decimal("0"),
            limit_per_period=Decimal("999999999"),
        )
        group.allowed_traffic.add(traffic)
        card = _virtual_card()
        PaymentDetails.objects.create(
            group=group,
            status=1,
            amount=Decimal("9999999"),
            card_number=card,
            deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
            sberpay_enabled=False,
            sbp_enabled=False,
        )
        print(f"  + group {group.id} card …{card[-4:]}")
        return group

    group.status = 1
    group.in_active = True
    group.current_volume = Decimal("0")
    group.amount = Decimal("9999999")
    group.auto_live = timezone.now()
    group.save()
    group.allowed_traffic.add(traffic)

    detail = PaymentDetails.objects.filter(group=group, status=1).first()
    if detail is None:
        card = _virtual_card()
        PaymentDetails.objects.create(
            group=group,
            status=1,
            amount=Decimal("9999999"),
            card_number=card,
            deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
            sberpay_enabled=False,
            sbp_enabled=False,
        )
        print(f"  + PaymentDetails on group {group.id}")
    else:
        print(f"  ~ group {group.id} card …{str(detail.card_number or '')[-4:]}")
    return group


def ensure_merchant_solution(merchant: Merchant, ps: PaymentSystem, traffic: TrafficType) -> None:
    merchant.payment_systems.add(ps)
    for ftd in (False, True):
        sol, created = MerchantSolution.objects.get_or_create(
            merchant=merchant,
            payment_system=ps,
            ftd=ftd,
            defaults={
                "status": 1,
                "traffic": traffic,
                "mdr_in": Decimal("2.5"),
                "mdr_out": Decimal("3.0"),
                "autoclose_arbitrage": False,
                **LIMITS,
            },
        )
        if not created:
            sol.status = 1
            sol.traffic = traffic
            sol.min_limit_in = LIMITS["min_limit_in"]
            sol.max_limit_in = LIMITS["max_limit_in"]
            sol.save(update_fields=["status", "traffic", "min_limit_in", "max_limit_in"])
        tag = "+" if created else "~"
        print(f"  {tag} MerchantSolution lunatrixpay ftd={ftd} ps={PS_NAME}")


def deactivate_other_groups(ps: PaymentSystem, *, keep_username: str) -> None:
    keep_trader = Trader.objects.filter(user__username=keep_username).first()
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
    print(f"Appeal test routing: {MERCHANT_USERNAME} → {PS_NAME} → {TRADER_USERNAME}")
    print("=" * 60)

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        raise RuntimeError("Currency KZT not found")

    ps = ensure_payment_system(kzt)
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    trader_user = User.objects.filter(username=TRADER_USERNAME).first()
    if trader_user is None:
        raise RuntimeError(f"Trader user {TRADER_USERNAME!r} not found — создайте трейдера в админке")
    trader = Trader.objects.filter(user=trader_user).select_related("team").first()
    if trader is None:
        raise RuntimeError(f"Trader profile for {TRADER_USERNAME!r} not found")

    if trader.team_id:
        TraderTeamRates.objects.get_or_create(
            team=trader.team,
            payment_system=ps,
            defaults={"mdr_in": Decimal("5"), "mdr_out": Decimal("2.5")},
        )

    if trader.balance_usdt.amount < Decimal("1000"):
        trader.balance_usdt.amount = Decimal("50000")
        trader.balance_usdt.save(update_fields=["amount"])
        print(f"  + topped balance_usdt for {TRADER_USERNAME}")

    ensure_trader_group(trader, ps, kzt, traffic)
    deactivate_other_groups(ps, keep_username=TRADER_USERNAME)

    merchant = Merchant.objects.filter(user__username=MERCHANT_USERNAME).first()
    if merchant is None:
        raise RuntimeError(f"Merchant {MERCHANT_USERNAME!r} not found")
    ensure_merchant_solution(merchant, ps, traffic)

    print("")
    print("Done.")
    print(f"  • Pay-in: merchant={MERCHANT_USERNAME}, payment_system={PS_NAME}, currency=KZT")
    print(
        f"  • diagnose: python manage.py diagnose_routing {MERCHANT_USERNAME} "
        f"--ps {PS_NAME} --amount 10000 --ftd false"
    )
    print("  • После создания заявки — апелляция в Telegram-чате мерчанта (чек + pay_in UUID)")


run()
