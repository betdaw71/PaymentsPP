"""
Создать контрагентов апелляций и пользователя appeal_bot для API.

Тестовый стенд (по умолчанию):
  MERCHANT_USERNAME=lunatrixpay
  TEST_TRADER_USERNAME=kzt_c2c_test

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_appeal_counterparty.py

Или с переопределением:
  docker compose exec -T \
    -e MERCHANT_USERNAME=lunatrixpay \
    -e TEST_TRADER_USERNAME=kzt_c2c_test \
    app python manage.py shell < titanpay/basics/shell_create_appeal_counterparty.py
"""
import os
import uuid

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from appeals.models import AppealCounterparty, AppealCounterpartyRole
from basics.models import Trader
from bots.models import TGBot
from merchant.models import Merchant
from payments.psp_payin import _psp_provider_for_trader

MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "lunatrixpay")
MERCHANT_COUNTERPARTY_NAME = os.environ.get("MERCHANT_COUNTERPARTY_NAME", "LunatrixPay")
TEST_TRADER_USERNAME = os.environ.get("TEST_TRADER_USERNAME", "kzt_c2c_test")
TEST_TRADER_COUNTERPARTY_NAME = os.environ.get(
    "TEST_TRADER_COUNTERPARTY_NAME",
    f"Test trader {TEST_TRADER_USERNAME}",
)

PROVIDERS = [
    {"name": "BotonPay", "psp_provider": "botonpay"},
    {"name": "BitZone", "psp_provider": "bitzone"},
    {"name": "Protocol", "psp_provider": "protocol"},
    {"name": "GiPay", "psp_provider": "gipay"},
    {"name": "VisionX Pay", "psp_provider": "visionx"},
]


def ensure_appeal_bot_user():
    user, created = User.objects.get_or_create(username="appeal_bot_user")
    if created:
        user.set_password(str(uuid.uuid4()))
        user.save()
    TGBot.objects.get_or_create(user=user)
    token, _ = Token.objects.get_or_create(user=user)
    print(f"appeal_bot_user API token: {token.key}")
    print("→ добавьте в .env: APPEAL_BOT_API_TOKEN=<этот токен>")
    return token.key


def ensure_merchant_counterparty():
    merchant = Merchant.objects.filter(user__username=MERCHANT_USERNAME).first()
    if merchant is None:
        print(f"ERROR: merchant {MERCHANT_USERNAME!r} not found")
        return None

    cp, created = AppealCounterparty.objects.get_or_create(
        merchant=merchant,
        role=AppealCounterpartyRole.MERCHANT,
        defaults={"name": MERCHANT_COUNTERPARTY_NAME},
    )
    print(f"Merchant {cp.name}: uuid={cp.id}")
    print(f"  → в группе мерчанта: /init {cp.id}")
    return cp


def ensure_test_trader_counterparty():
    trader = Trader.objects.filter(user__username=TEST_TRADER_USERNAME).first()
    if trader is None:
        print(f"WARN: trader {TEST_TRADER_USERNAME!r} not found — пропускаем провайдерский контрагент")
        return None

    psp_key, _ = _psp_provider_for_trader(trader)
    if psp_key:
        cp, created = AppealCounterparty.objects.get_or_create(
            role=AppealCounterpartyRole.PROVIDER,
            psp_provider=psp_key,
            defaults={"name": f"{TEST_TRADER_COUNTERPARTY_NAME} ({psp_key})"},
        )
        print(f"Provider PSP {psp_key}: uuid={cp.id}")
        print(f"  → в группе провайдера: /init {cp.id}")
        return cp

    cp, created = AppealCounterparty.objects.get_or_create(
        role=AppealCounterpartyRole.PROVIDER,
        trader_username=TEST_TRADER_USERNAME,
        defaults={"name": TEST_TRADER_COUNTERPARTY_NAME},
    )
    print(f"Provider local trader {TEST_TRADER_USERNAME}: uuid={cp.id}")
    print(f"  → в группе провайдера: /init {cp.id}")
    return cp


def ensure_provider_counterparties():
    for item in PROVIDERS:
        cp, created = AppealCounterparty.objects.get_or_create(
            role=AppealCounterpartyRole.PROVIDER,
            psp_provider=item["psp_provider"],
            defaults={"name": item["name"]},
        )
        print(f"Provider {item['name']}: uuid={cp.id}")


print("=== Appeal bot setup ===")
ensure_appeal_bot_user()
ensure_merchant_counterparty()
ensure_test_trader_counterparty()
print("\n--- Все PSP-провайдеры (если нужны prod-группы) ---")
ensure_provider_counterparties()
print("\nГотово.")
