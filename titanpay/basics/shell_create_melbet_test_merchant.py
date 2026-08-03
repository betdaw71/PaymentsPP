"""
Тестовый кабинет Melbet (KZT / C2CKZT) — дубль prod melbet с известным паролем.

Не трогает пользователя melbet, если он уже есть.

Запуск на сервере:
  docker compose exec app python manage.py shell < basics/shell_create_melbet_test_merchant.py

Или в shell:
  exec(open("basics/shell_create_melbet_test_merchant.py").read())
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
from merchant.kzt_settlement import MELBET_TEST_USERNAME, ensure_kzt_balances
from merchant.models import Merchant, MerchantSolution
from payments.integrations.melbet.models import MelbetIntegrationConfig
from payments.models import APIKeys
from trade.models import Address

DEFAULT_PASSWORD = "Melbet_Test_2026!"

KZT_METHOD_MAP = {
    "default_kzt": {"payment_system": "C2CKZT", "currency": "KZT"},
    "card2card_kzt": {"payment_system": "C2CKZT", "currency": "KZT"},
    "card2card_kzt_kaspi": {"payment_system": "C2CKZT", "currency": "KZT"},
    "default": {"payment_system": "C2CKZT", "currency": "KZT"},
}

SETTINGS = {
    "username": MELBET_TEST_USERNAME,
    "email": "melbet-test@example.local",
    "first_name": "Melbet Test",
    "telegram": "@melbet_test",
    "phone": "+77000000001",
    "mdr": {"mdr_in": Decimal("2.5"), "mdr_out": Decimal("3.0")},
    "limits": {
        "min_limit_in": Decimal("1000"),
        "max_limit_in": Decimal("1000000"),
        "min_limit_out": Decimal("1000"),
        "max_limit_out": Decimal("1000000"),
    },
    "ps": {
        "name": "C2CKZT",
        "usdt_exchange_rate": Decimal("500.00"),
        "expired_time_in": datetime.timedelta(minutes=15),
        "arbitrage_time_in": datetime.timedelta(minutes=30),
        "auto_close_amount": Decimal("-1"),
        "expired_time_out": datetime.timedelta(minutes=15),
        "confirm_time_out": datetime.timedelta(minutes=15),
        "constrain_time_out": datetime.timedelta(hours=4),
        "in_on": True,
        "out_on": True,
        "sbp_compatible": False,
        "required_fields": {
            "card_number": {"regex": r"^\d{16}$", "pattern": "16-digit card"},
            "owner": {"regex": r"^.+$", "pattern": "Card holder name"},
            "bank": {"regex": r"^.+$", "pattern": "Bank name"},
        },
    },
}


def _deposit_address(username: str) -> str:
    try:
        from basics.utils import generate_address

        address = generate_address()
        if address:
            return address
    except Exception as exc:
        print(f"  ! crypto service unavailable ({exc}); placeholder address")
    return f"melbet_test_{username}_{uuid.uuid4().hex[:16]}"


@transaction.atomic
def run(password: str = DEFAULT_PASSWORD) -> dict:
    print("=" * 60)
    print("Melbet test merchant (KZT / C2CKZT)")
    print("=" * 60)

    language, _ = Language.objects.get_or_create(name="English")
    traffic, _ = TrafficType.objects.get_or_create(name="Standard", defaults={"risk_level": 0})
    currency, _ = Currency.objects.get_or_create(
        symbol="KZT",
        defaults={"name": "Kazakhstani Tenge"},
    )
    ps_cfg = SETTINGS["ps"]
    ps, ps_created = PaymentSystem.objects.get_or_create(
        name=ps_cfg["name"],
        currency=currency,
        defaults={
            "usdt_exchange_rate": ps_cfg["usdt_exchange_rate"],
            "expired_time_in": ps_cfg["expired_time_in"],
            "arbitrage_time_in": ps_cfg["arbitrage_time_in"],
            "auto_close_amount": ps_cfg["auto_close_amount"],
            "expired_time_out": ps_cfg["expired_time_out"],
            "confirm_time_out": ps_cfg["confirm_time_out"],
            "constrain_time_out": ps_cfg["constrain_time_out"],
            "in_on": ps_cfg["in_on"],
            "out_on": ps_cfg["out_on"],
            "sbp_compatible": ps_cfg["sbp_compatible"],
            "required_fields": ps_cfg["required_fields"],
        },
    )
    print(f"{'+' if ps_created else '~'} PaymentSystem: {ps.name}")

    spec = SETTINGS
    user, user_created = User.objects.get_or_create(
        username=spec["username"],
        defaults={"email": spec["email"], "first_name": spec["first_name"]},
    )
    if user_created:
        user.set_password(password)
        user.save()
        print(f"  + User: {spec['username']}")
    else:
        user.set_password(password)
        user.save(update_fields=["password"])
        print(f"  ~ User exists (password reset): {spec['username']}")

    if hasattr(user, "merchant"):
        merchant = user.merchant
        print(f"  ~ Merchant: {merchant.id}")
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
        Address.objects.create(balance=balance, address_public=_deposit_address(spec["username"]))
        print(f"  + Merchant: {merchant.id}")

    ensure_kzt_balances(merchant)
    merchant.refresh_from_db()
    merchant.payment_systems.add(ps)

    for ftd in (False, True):
        MerchantSolution.objects.get_or_create(
            merchant=merchant,
            payment_system=ps,
            ftd=ftd,
            defaults={
                "status": 1,
                "traffic": traffic,
                "mdr_in": spec["mdr"]["mdr_in"],
                "mdr_out": spec["mdr"]["mdr_out"],
                "autoclose_arbitrage": False,
                **spec["limits"],
            },
        )

    public_key, secret_key = MelbetIntegrationConfig.generate_keys()
    melbet_cfg, cfg_created = MelbetIntegrationConfig.objects.get_or_create(
        merchant=merchant,
        defaults={
            "public_key": public_key,
            "secret_key": secret_key,
            "active": True,
            "whitelist_on": False,
            "method_map": KZT_METHOD_MAP,
            "default_ftd": False,
        },
    )
    if not cfg_created:
        melbet_cfg.method_map = KZT_METHOD_MAP
        melbet_cfg.active = True
        melbet_cfg.save(update_fields=["method_map", "active"])
        print("  ~ MelbetIntegrationConfig updated")
    else:
        print("  + MelbetIntegrationConfig created")

    api_key = APIKeys.create(merchant=merchant)
    Token.objects.filter(user=user).delete()
    token = Token.objects.create(user=user)

    result = {
        "merchant_id": str(merchant.id),
        "username": spec["username"],
        "password": password,
        "panel_login": spec["username"],
        "api_token": token.key,
        "private_key": str(api_key.private_key),
        "melbet_public_key": melbet_cfg.public_key,
        "melbet_secret_key": melbet_cfg.secret_key,
        "balance_kzt": str(merchant.balance_kzt.amount),
        "balance_usdt": str(merchant.balance.amount if merchant.balance else 0),
    }

    print("\n" + "=" * 60)
    print("ГОТОВО — вход в кабинет мерчанта (фронт):")
    print("=" * 60)
    for key, label in (
        ("panel_login", "Логин"),
        ("password", "Пароль"),
        ("merchant_id", "Merchant ID"),
        ("api_token", "API Token (DRF)"),
        ("private_key", "Private key (merchant API)"),
        ("melbet_public_key", "Melbet integration public_key"),
        ("melbet_secret_key", "Melbet integration secret_key"),
        ("balance_kzt", "balance_kzt"),
        ("balance_usdt", "balance USDT"),
    ):
        print(f"  {label}: {result[key]}")
    print(
        "\nKZT prepaid: exec(open('basics/shell_melbet_kzt_balance.py').read()); "
        f"set_balance('-500000', username='{MELBET_TEST_USERNAME}')"
    )
    return result


if __name__ == "__main__":
    run()
else:
    print("Запустите: run()  # password по умолчанию Melbet_Test_2026!")
