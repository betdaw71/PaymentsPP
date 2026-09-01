"""
Существующий мерчант lunatrixpay: RUB PS + MerchantSolution + группы syndicate1 (тест Syndicate).

Не трогает другие валюты мерчанта (payment_systems.add, не set).
Не перевыпускает API token / private key.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_ensure_lunatrix_rub_syndicate.py

Перед: shell_create_syndicate_trader.py + SYNDICATE_* в .env

Env: LUNATRIX_MERCHANT_USERNAME (default lunatrixpay), LUNATRIX_RUB_MDR_IN, лимиты.
"""
from __future__ import annotations

import datetime
import os
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
from payments.syndicate_client import syndicate_trader_username
from titanpay.settings import (
    ALFA_NAME,
    C2C_NAME,
    INTERBANK_NAME,
    OTP_NAME,
    SBERDEP_NAME,
    SBERPAY_NAME,
    SBER_NAME,
    SBP_NAME,
    TBANK_NAME,
)

MERCHANT_USERNAME = os.environ.get("LUNATRIX_MERCHANT_USERNAME", "lunatrixpay")
TRAFFIC_NAME = "Standard"
MDR_IN = Decimal(os.environ.get("LUNATRIX_RUB_MDR_IN", "7.5"))
MDR_OUT = Decimal(os.environ.get("LUNATRIX_RUB_MDR_OUT", "7.5"))

RU_PAYMENT_SYSTEMS = (
    C2C_NAME,
    SBP_NAME,
    SBER_NAME,
    SBERPAY_NAME,
    SBERDEP_NAME,
    TBANK_NAME,
    ALFA_NAME,
    OTP_NAME,
    INTERBANK_NAME,
)

LIMITS = {
    "min_limit_in": Decimal(os.environ.get("LUNATRIX_RUB_MIN_IN", "500")),
    "max_limit_in": Decimal(os.environ.get("LUNATRIX_RUB_MAX_IN", "500000")),
    "min_limit_out": Decimal(os.environ.get("LUNATRIX_RUB_MIN_OUT", "500")),
    "max_limit_out": Decimal(os.environ.get("LUNATRIX_RUB_MAX_OUT", "500000")),
}

PS_DEFAULTS = {
    "usdt_exchange_rate": Decimal("100"),
    "expired_time_in": datetime.timedelta(minutes=30),
    "arbitrage_time_in": datetime.timedelta(minutes=30),
    "auto_close_amount": Decimal("-1"),
    "expired_time_out": datetime.timedelta(minutes=15),
    "confirm_time_out": datetime.timedelta(minutes=15),
    "constrain_time_out": datetime.timedelta(hours=4),
    "in_on": True,
    "out_on": True,
}

CARD_FIELDS = {
    "card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"},
    "owner": {"regex": r"^.+$", "pattern": "Card holder"},
    "bank": {"regex": r"^.+$", "pattern": "Bank"},
}
SBP_FIELDS = {
    "phone": {"regex": r"^\+7\d{10}$", "pattern": "+7XXXXXXXXXX"},
    "owner": {"regex": r"^.+$", "pattern": "Card holder"},
    "bank": {"regex": r"^.+$", "pattern": "Bank"},
}


def _required_fields(ps_name: str) -> dict:
    return SBP_FIELDS if ps_name == SBP_NAME else CARD_FIELDS


def ensure_payment_system(currency: Currency, name: str) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=name, currency=currency).first()
    sbp = name == SBP_NAME
    defaults = {**PS_DEFAULTS, "sbp_compatible": sbp, "required_fields": _required_fields(name)}
    if ps:
        if not ps.in_on:
            ps.in_on = True
            ps.save(update_fields=["in_on"])
        print(f"  ~ PaymentSystem {name}")
        return ps
    ps = PaymentSystem.objects.create(name=name, currency=currency, **defaults)
    print(f"  + PaymentSystem {name}")
    return ps


def ensure_syndicate_group(trader: Trader, currency: Currency, ps: PaymentSystem, traffic: TrafficType) -> None:
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=ps, currency=currency).first()
    if group:
        if group.status != 1 or not group.in_active:
            group.status = 1
            group.in_active = True
            group.save(update_fields=["status", "in_active"])
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ syndicate group {ps.name}")
        return
    group = PaymentDetailsGroup.objects.create(
        owner=f"Syndicate {MERCHANT_USERNAME} {ps.name}",
        trader=trader,
        currency=currency,
        payment_system=ps,
        status=1,
        amount=Decimal("999999"),
        in_active=True,
        out_active=False,
        min_amount_out=Decimal("100"),
        max_amount_out=Decimal("5000000"),
        work_type="by_card",
        deposit_number_on=False,
        auto_live=timezone.now(),
    )
    group.allowed_traffic.add(traffic)
    import uuid
    card = "".join(c for c in ("4" + uuid.uuid4().hex[:15]) if c.isdigit())[:16].ljust(16, "0")
    PaymentDetails.objects.create(
        group=group,
        status=1,
        amount=Decimal("999999"),
        card_number=card,
        deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
        sberpay_enabled=False,
        sbp_enabled=False,
    )
    print(f"  + syndicate group {ps.name}")


@transaction.atomic
def run() -> None:
    print("=" * 60)
    print(f"{MERCHANT_USERNAME} — RUB Syndicate test setup")
    print("=" * 60)
    user = User.objects.filter(username=MERCHANT_USERNAME).first()
    if user is None or not hasattr(user, "merchant"):
        raise SystemExit(f"Merchant {MERCHANT_USERNAME!r} not found")
    merchant = user.merchant
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    currency, _ = Currency.objects.get_or_create(symbol="RUB", defaults={"name": "Russian Ruble"})
    print("\nRUB payment systems:")
    payment_systems = [ensure_payment_system(currency, n) for n in RU_PAYMENT_SYSTEMS]
    trader = Trader.objects.filter(user__username=syndicate_trader_username()).select_related("team").first()
    if trader is None:
        raise SystemExit("Run shell_create_syndicate_trader.py first")
    print(f"\nSyndicate ({syndicate_trader_username()}) groups:")
    team = trader.team
    for ps in payment_systems:
        TraderTeamRates.objects.get_or_create(
            team=team,
            payment_system=ps,
            defaults={"mdr_in": Decimal("1"), "mdr_out": Decimal("1")},
        )
        ensure_syndicate_group(trader, currency, ps, traffic)
    print(f"\nMerchant {MERCHANT_USERNAME}:")
    for ps in payment_systems:
        merchant.payment_systems.add(ps)
    print(f"  ~ linked {len(payment_systems)} RUB PS (other currencies unchanged)")
    for ps in payment_systems:
        for ftd in (False, True):
            sol, created = MerchantSolution.objects.get_or_create(
                merchant=merchant,
                payment_system=ps,
                ftd=ftd,
                defaults={
                    "status": 1,
                    "traffic": traffic,
                    "mdr_in": MDR_IN,
                    "mdr_out": MDR_OUT,
                    "autoclose_arbitrage": False,
                    **LIMITS,
                },
            )
            if not created:
                sol.status = 1
                sol.mdr_in = MDR_IN
                sol.mdr_out = MDR_OUT
                for k, v in LIMITS.items():
                    setattr(sol, k, v)
                sol.save()
            print(f"  {'+' if created else '~'} {ps.name} ftd={ftd} mdr_in={MDR_IN}%")
    print("\nГОТОВО")
    print(f"  diagnose: python manage.py diagnose_routing {MERCHANT_USERNAME} --ps C2C --amount 5000 --ftd false")
    print("  H2H: POST /api/v1/payments/in/h2h/  currency=RUB  payment_system=C2C  ftd=false")
    print(f"  amount must be in [{LIMITS['min_limit_in']}, {LIMITS['max_limit_in']}]")


run()
