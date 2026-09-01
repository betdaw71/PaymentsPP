"""
Django shell: мерчант BetOnGame (MMK / Мьянма) — тестовый и продовый кабинеты + API-креды.

Запуск:
  docker compose exec app python manage.py shell < basics/shell_create_betongame_merchant.py

Или в shell:
  exec(open("basics/shell_create_betongame_merchant.py").read())
  run()
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.authtoken.models import Token

from basics.models import Balance, Currency, Language, PaymentSystem, TrafficType
from merchant.models import Merchant, MerchantSolution
from payments.models import APIKeys
from trade.models import Address

# Пароль кабинета — сменить после первого входа.
DEFAULT_PASSWORD = "Bet0ngame_2026!"

SETTINGS = {
    "currency": {"name": "Myanmar Kyat", "symbol": "MMK"},
    "payment_systems": [
        {"name": "KBZPay", "usdt_exchange_rate": Decimal("3500.00")},
        {"name": "WavePay", "usdt_exchange_rate": Decimal("3500.00")},
        {"name": "C2CMMK", "usdt_exchange_rate": Decimal("3500.00")},
    ],
    "default_ps": {
        "expired_time_in": datetime.timedelta(minutes=10),
        "arbitrage_time_in": datetime.timedelta(minutes=30),
        "auto_close_amount": Decimal("-1"),
        "expired_time_out": datetime.timedelta(minutes=10),
        "confirm_time_out": datetime.timedelta(minutes=10),
        "constrain_time_out": datetime.timedelta(hours=4),
        "in_on": True,
        "out_on": True,
        "sbp_compatible": False,
    },
    "ps_required_fields": {
        "KBZPay": {
            "phone": {"regex": r"^\+95\d{7,12}$", "pattern": "Myanmar phone (+95...)"},
        },
        "WavePay": {
            "phone": {"regex": r"^\+95\d{7,12}$", "pattern": "Myanmar phone (+95...)"},
        },
        "C2CMMK": {
            "card_number": {"regex": r"^\d{16}$", "pattern": "16-digit card number"},
        },
    },
    "traffic": "Standard",
    "mdr": {"mdr_in": Decimal("2.5"), "mdr_out": Decimal("3.0")},
    "limits": {
        "min_limit_in": Decimal("5000"),
        "max_limit_in": Decimal("5000000"),
        "min_limit_out": Decimal("5000"),
        "max_limit_out": Decimal("5000000"),
    },
    "merchants": [
        {
            "env": "TEST",
            "username": "betongame_test",
            "email": "payment+test@betongame.com",
            "first_name": "BetOnGame Test",
            "telegram": "@betongame_test",
            "phone": "+959000000001",
        },
        {
            "env": "PROD",
            "username": "betongame",
            "email": "payment@betongame.com",
            "first_name": "BetOnGame",
            "telegram": "@betongame",
            "phone": "+959000000002",
        },
    ],
}


def _merchant_deposit_address(username: str) -> str:
    """USDT-адрес для пополнения баланса мерчанта. Fallback, если crypto-сервис недоступен."""
    try:
        from basics.utils import generate_address
        address = generate_address()
        if address:
            return address
    except Exception as exc:
        print(f"  ! crypto service unavailable ({exc}); using placeholder address")
    # Placeholder: заменить на реальный адрес после поднятия crypto-сервиса.
    return f"betongame_{username}_{uuid.uuid4().hex[:16]}"


def _ensure_payment_systems(currency: Currency, traffic: TrafficType) -> list[PaymentSystem]:
    systems: list[PaymentSystem] = []
    for ps_data in SETTINGS["payment_systems"]:
        name = ps_data["name"]
        defaults = {
            **SETTINGS["default_ps"],
            "usdt_exchange_rate": ps_data["usdt_exchange_rate"],
            "required_fields": SETTINGS["ps_required_fields"][name],
        }
        ps, created = PaymentSystem.objects.get_or_create(
            name=name,
            currency=currency,
            defaults=defaults,
        )
        if not created:
            changed = False
            for field, value in defaults.items():
                if getattr(ps, field) != value:
                    setattr(ps, field, value)
                    changed = True
            if changed:
                ps.save()
        systems.append(ps)
        print(f"  {'+' if created else '~'} PaymentSystem: {name}")
    return systems


def _ensure_merchant(
    *,
    spec: dict,
    language: Language,
    traffic: TrafficType,
    payment_systems: list[PaymentSystem],
    password: str,
) -> dict:
    user, user_created = User.objects.get_or_create(
        username=spec["username"],
        defaults={
            "email": spec["email"],
            "first_name": spec["first_name"],
        },
    )
    if user_created:
        user.set_password(password)
        user.save()
        print(f"  + User: {spec['username']}")
    else:
        print(f"  ~ User exists: {spec['username']}")
    if hasattr(user, "merchant"):
        merchant = user.merchant
        print(f"  ~ Merchant exists: {merchant.id}")
    else:
        balance = Balance.objects.create(type=0, amount=Decimal("0"))
        frozen = Balance.objects.create(type=1, amount=Decimal("0"))
        merchant = Merchant.objects.create(
            user=user,
            language=language,
            balance=balance,
            frozen_balance=frozen,
            telegram=spec["telegram"],
            phone=spec["phone"],
        )
        Address.objects.create(
            balance=balance,
            address_public=_merchant_deposit_address(spec["username"]),
        )
        print(f"  + Merchant: {merchant.id}")
    merchant.payment_systems.set(payment_systems)
    for ps in payment_systems:
        for ftd in (False, True):
            MerchantSolution.objects.get_or_create(
                merchant=merchant,
                payment_system=ps,
                ftd=ftd,
                defaults={
                    "status": 1,
                    "traffic": traffic,
                    "mdr_in": SETTINGS["mdr"]["mdr_in"],
                    "mdr_out": SETTINGS["mdr"]["mdr_out"],
                    "autoclose_arbitrage": False,
                    **SETTINGS["limits"],
                },
            )
    api_key = APIKeys.create(merchant=merchant)
    Token.objects.filter(user=user).delete()
    token = Token.objects.create(user=user)
    return {
        "env": spec["env"],
        "merchant_id": str(merchant.id),
        "username": spec["username"],
        "email": spec["email"],
        "password": password,
        "api_token": token.key,
        "private_key": str(api_key.private_key),
        "payment_systems": [ps.name for ps in payment_systems],
    }


@transaction.atomic
def run(password: str = DEFAULT_PASSWORD) -> list[dict]:
    print("=" * 60)
    print("BetOnGame — создание MMK + тест/прод кабинетов")
    print("=" * 60)
    language, _ = Language.objects.get_or_create(name="English")
    traffic, _ = TrafficType.objects.get_or_create(
        name=SETTINGS["traffic"],
        defaults={"risk_level": 0},
    )
    currency, created = Currency.objects.get_or_create(
        symbol=SETTINGS["currency"]["symbol"],
        defaults={"name": SETTINGS["currency"]["name"]},
    )
    print(f"{'+' if created else '~'} Currency: {currency.symbol} ({currency.name})")
    print("\nПлатёжные системы:")
    payment_systems = _ensure_payment_systems(currency, traffic)
    results: list[dict] = []
    for spec in SETTINGS["merchants"]:
        print(f"\n--- Кабинет {spec['env']} ({spec['username']}) ---")
        results.append(
            _ensure_merchant(
                spec=spec,
                language=language,
                traffic=traffic,
                payment_systems=payment_systems,
                password=password,
            )
        )
    print("\n" + "=" * 60)
    print("ГОТОВО. Данные для интеграции:")
    print("=" * 60)
    for row in results:
        print(f"\n[{row['env']}] {row['username']}")
        print(f"  Merchant ID:     {row['merchant_id']}")
        print(f"  Email:           {row['email']}")
        print(f"  Пароль кабинета: {row['password']}")
        print(f"  API Token:       {row['api_token']}")
        print(f"  Private key:     {row['private_key']}")
        print(f"  Payment systems: {', '.join(row['payment_systems'])}")
        print(f"  Лимиты pay-in:   {SETTINGS['limits']['min_limit_in']} – {SETTINGS['limits']['max_limit_in']} MMK")
    print(
        "\nПримечание: для реальных pay-in нужны трейдеры/PSP с реквизитами MMK "
        "(отдельная настройка routing/трейдеров)."
    )
    return results


if __name__ == "__main__":
    run()
else:
    print("Запустите: run()")
