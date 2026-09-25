"""
Django shell: мерчант nspay (RUB) — Syndicate, БТ РФ (C2C/SBP + основные банки).

Ставки pay-in по сумме чека:
  5 000 – 9 999.99 RUB → 11%
  10 000+ RUB          → 10.5%
(логика в merchant/tiered_mdr.py, username=nspay)

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_nspay_merchant.py

Перед этим: syndicate1 + SYNDICATE_* в .env (shell_create_syndicate_trader.py).

Env: NSPAY_MERCHANT_USERNAME, NSPAY_MERCHANT_PASSWORD, NSPAY_RUB_MIN_IN (default 5000).
"""
from __future__ import annotations

import datetime
import os
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from basics.models import (
    Balance,
    Currency,
    Language,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeamRates,
    TrafficType,
)
from merchant.models import Merchant, MerchantSolution
from payments.models import APIKeys
from payments.syndicate_client import syndicate_trader_username
from trade.models import Address
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

MERCHANT_USERNAME = os.environ.get("NSPAY_MERCHANT_USERNAME", "nspay")
DEFAULT_PASSWORD = os.environ.get("NSPAY_MERCHANT_PASSWORD", "NSPay_Merchant_2026!")
TRAFFIC_NAME = "Standard"
# Базовая ставка в MerchantSolution (фактическая — по tiered_mdr).
MDR_IN = Decimal("11")
MDR_OUT = Decimal("11")

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
    "min_limit_in": Decimal(os.environ.get("NSPAY_RUB_MIN_IN", "5000")),
    "max_limit_in": Decimal(os.environ.get("NSPAY_RUB_MAX_IN", "500000")),
    "min_limit_out": Decimal(os.environ.get("NSPAY_RUB_MIN_OUT", "5000")),
    "max_limit_out": Decimal(os.environ.get("NSPAY_RUB_MAX_OUT", "500000")),
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
    if ps_name == SBP_NAME:
        return SBP_FIELDS
    return CARD_FIELDS


def _deposit_address(username: str) -> str:
    try:
        from basics.utils import generate_address

        address = generate_address()
        if address:
            return address
    except Exception as exc:
        print(f"  ! crypto service unavailable ({exc}); placeholder address")
    return f"nspay_{username}_{uuid.uuid4().hex[:16]}"


def ensure_payment_system(currency: Currency, name: str) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=name, currency=currency).first()
    sbp = name == SBP_NAME
    defaults = {
        **PS_DEFAULTS,
        "sbp_compatible": sbp,
        "required_fields": _required_fields(name),
    }
    if ps:
        changed = False
        for field, value in defaults.items():
            if getattr(ps, field) != value:
                setattr(ps, field, value)
                changed = True
        if not ps.in_on:
            ps.in_on = True
            changed = True
        if changed:
            ps.save()
        print(f"  ~ PaymentSystem {name} ({ps.id})")
        return ps
    ps = PaymentSystem.objects.create(name=name, currency=currency, **defaults)
    print(f"  + PaymentSystem {name} ({ps.id})")
    return ps


def ensure_syndicate_virtual_group(trader: Trader, currency: Currency, ps: PaymentSystem, traffic: TrafficType, label: str):
    group = PaymentDetailsGroup.objects.filter(
        trader=trader, payment_system=ps, currency=currency
    ).first()
    if group:
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
        print(f"  ~ syndicate group {label} ({group.id})")
        return group

    group = PaymentDetailsGroup.objects.create(
        owner=f"Syndicate {MERCHANT_USERNAME} {label}",
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
    print(f"  + syndicate group {label} ({group.id})")
    return group


def ensure_syndicate_routing(trader: Trader, currency: Currency, traffic: TrafficType, ps_list: list[PaymentSystem]) -> None:
    team = trader.team
    for ps in ps_list:
        TraderTeamRates.objects.get_or_create(
            team=team,
            payment_system=ps,
            defaults={"mdr_in": Decimal("1"), "mdr_out": Decimal("1")},
        )
        ensure_syndicate_virtual_group(trader, currency, ps, traffic, ps.name)


@transaction.atomic
def run(password: str = DEFAULT_PASSWORD) -> dict:
    print("=" * 60)
    print(f"{MERCHANT_USERNAME} — RUB / Syndicate (tiered MDR)")
    print("=" * 60)

    language, _ = Language.objects.get_or_create(name="English")
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    currency, _ = Currency.objects.get_or_create(symbol="RUB", defaults={"name": "Russian Ruble"})
    print("~ Currency RUB")

    print("\nПлатёжные системы (RUB):")
    payment_systems = [ensure_payment_system(currency, name) for name in RU_PAYMENT_SYSTEMS]

    trader = Trader.objects.filter(user__username=syndicate_trader_username()).select_related("team").first()
    if trader is None:
        raise SystemExit(
            f"Trader {syndicate_trader_username()} not found — run shell_create_syndicate_trader.py first"
        )
    print(f"\nРоутинг Syndicate ({syndicate_trader_username()}):")
    ensure_syndicate_routing(trader, currency, traffic, payment_systems)

    print(f"\nМерчант {MERCHANT_USERNAME}:")
    email = f"{MERCHANT_USERNAME}@merchant.local"
    user, user_created = User.objects.get_or_create(
        username=MERCHANT_USERNAME,
        defaults={"email": email, "first_name": "NSPay"},
    )
    if user_created:
        user.set_password(password)
        user.save()
        print(f"  + User {MERCHANT_USERNAME}")
    else:
        print(f"  ~ User {MERCHANT_USERNAME} (ключи API не перевыпускаются)")

    merchant_created = False
    if hasattr(user, "merchant"):
        merchant = user.merchant
        print(f"  ~ Merchant {merchant.id}")
    else:
        balance = Balance.objects.create(type=0, amount=Decimal("0"))
        frozen = Balance.objects.create(type=1, amount=Decimal("0"))
        merchant = Merchant.objects.create(
            user=user,
            language=language,
            balance=balance,
            frozen_balance=frozen,
            telegram=f"@{MERCHANT_USERNAME}",
            phone="+79000000000",
        )
        Address.objects.create(balance=balance, address_public=_deposit_address(MERCHANT_USERNAME))
        merchant_created = True
        print(f"  + Merchant {merchant.id}")

    merchant.payment_systems.set(payment_systems)

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
            tag = "+" if created else "~"
            print(f"  {tag} MerchantSolution ps={ps.name} ftd={ftd}")

    if user_created or merchant_created:
        api_key = APIKeys.create(merchant=merchant)
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
    else:
        api_key = merchant.api_keys.filter(active=True).order_by("-created_at").first()
        if api_key is None:
            api_key = APIKeys.create(merchant=merchant)
        token, _ = Token.objects.get_or_create(user=user)

    print("\n" + "=" * 60)
    print(f"ГОТОВО — {MERCHANT_USERNAME}")
    print("=" * 60)
    print(f"  Merchant ID:  {merchant.id}")
    print(f"  Username:     {MERCHANT_USERNAME}")
    print(f"  Password:     {password}")
    print(f"  API Token:    {token.key}")
    print(f"  Private key:  {api_key.private_key}")
    print("  Pay-in MDR:   5k–10k → 11%; 10k+ → 10.5% (tiered_mdr)")
    print(f"  Payment PS:   {', '.join(RU_PAYMENT_SYSTEMS)}")
    print(f"  Limits in:    {LIMITS['min_limit_in']} – {LIMITS['max_limit_in']} RUB")
    print("\nH2H: POST /api/v1/payments/in/h2h/  currency=RUB  payment_system=C2C  ftd=false")
    print("diagnose: python manage.py diagnose_routing nspay --ps C2C --amount 7500 --ftd false")

    return {
        "merchant_id": str(merchant.id),
        "username": MERCHANT_USERNAME,
        "api_token": token.key,
        "private_key": str(api_key.private_key),
    }


run()
