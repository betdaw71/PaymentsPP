"""
Тест PayPlat: C2CKZTTEST → только payplat1.

  - активирует виртуальную группу payplat1 на C2CKZTTEST
  - отключает C2C и C2CKZT у payplat1
  - отключает другие PSP-трейдеры на C2CKZTTEST
  - MerchantSolution у тестового мерчанта

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_payplat_c2ckzttest_routing.py

Проверка:
  docker compose exec -T app python manage.py diagnose_routing lunatrixpay --ps C2CKZTTEST --amount 7000 --ftd false
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from basics.models import (
    Currency,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeam,
    TraderTeamRates,
    TrafficType,
)
from merchant.models import Merchant, MerchantSolution
from payments.payplat_client import payplat_trader_username
from payments.psp_payin import psp_trader_usernames

PS_NAME = (getattr(settings, "PAYPLAT_TEST_PS_NAME", None) or "C2CKZTTEST").strip()
MERCHANT_USERNAME = "lunatrixpay"
TRAFFIC_NAME = "Standard"
TEAM_NAME = "PayPlat Agg"
GROUP_OWNER = "PayPlat C2CKZTTEST test"
LIMITS = {
    "min_limit_in": Decimal("1000"),
    "max_limit_in": Decimal("500000"),
    "min_limit_out": Decimal("1000"),
    "max_limit_out": Decimal("500000"),
}
PAYPLAT_PS_NAMES = ("C2C", "C2CKZT", "C2CKZTTEST")


def ensure_payment_system(kzt: Currency) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
    if ps:
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


def ensure_payplat_virtual_group(trader: Trader, ps: PaymentSystem, kzt: Currency, traffic: TrafficType):
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=ps, currency=kzt).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner=GROUP_OWNER,
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
        print(f"  + virtual group {PS_NAME} ({group.id})")
        return group

    changed = False
    for field, val in (("status", 1), ("in_active", True), ("current_volume", Decimal("0"))):
        if getattr(group, field) != val:
            setattr(group, field, val)
            changed = True
    if changed:
        group.save()
    if PaymentDetails.objects.filter(group=group, status=1).count() == 0:
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
        print(f"  + PaymentDetails on group {group.id}")
    else:
        print(f"  ~ virtual group {PS_NAME} ({group.id}) in_active=True")
    return group


def set_payplat_groups_active(*, trader: Trader, active_ps_name: str) -> None:
    """У payplat1 активна только одна PS (C2CKZTTEST для теста)."""
    for group in PaymentDetailsGroup.objects.filter(trader=trader).select_related("payment_system"):
        ps_name = group.payment_system.name if group.payment_system else ""
        if ps_name not in PAYPLAT_PS_NAMES:
            continue
        should_active = ps_name == active_ps_name
        if group.in_active != should_active:
            group.in_active = should_active
            group.save(update_fields=["in_active"])
            print(f"  ~ payplat1 {ps_name}: in_active={should_active}")


def deactivate_other_psp_groups_on_test_ps(ps: PaymentSystem, *, keep_username: str) -> None:
    keep_trader = Trader.objects.filter(user__username=keep_username).first()
    qs = PaymentDetailsGroup.objects.filter(payment_system=ps, in_active=True).select_related("trader__user")
    if keep_trader:
        qs = qs.exclude(trader_id=keep_trader.id)
    psp_names = psp_trader_usernames()
    for group in qs:
        uname = group.trader.user.username if group.trader and group.trader.user else ""
        if uname in psp_names:
            group.in_active = False
            group.save(update_fields=["in_active"])
            print(f"  - deactivated C2CKZTTEST group {group.id} trader={uname}")


def ensure_merchant_solution(merchant: Merchant, ps: PaymentSystem, traffic: TrafficType):
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
        print(f"  {tag} MerchantSolution ftd={ftd} ps={PS_NAME}")


@transaction.atomic
def run(merchant_username: str = MERCHANT_USERNAME) -> None:
    print("=" * 60)
    print(f"PayPlat test routing: PS={PS_NAME} merchant={merchant_username}")
    print("=" * 60)

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        raise RuntimeError("Currency KZT not found")

    ps = ensure_payment_system(kzt)
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
        defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")},
    )

    ensure_payplat_virtual_group(trader, ps, kzt, traffic)
    set_payplat_groups_active(trader=trader, active_ps_name=PS_NAME)
    deactivate_other_psp_groups_on_test_ps(ps, keep_username=payplat_trader_username())

    try:
        merchant = Merchant.objects.get(user__username=merchant_username)
    except Merchant.DoesNotExist as exc:
        raise RuntimeError(f"Merchant {merchant_username!r} not found") from exc

    ensure_merchant_solution(merchant, ps, traffic)

    print("\nDone.")
    print(f"  • payplat1: active only {PS_NAME}")
    print(f"  • diagnose: diagnose_routing {merchant_username} --ps {PS_NAME} --amount 7000 --ftd false")
    print("  • pay-in: payment_system=C2CKZTTEST, currency=KZT")


run()
