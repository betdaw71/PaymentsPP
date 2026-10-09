"""
Апелляции PayPlat: appeal_bot_user + контрагенты мерчанта и провайдера payplat.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_payplat_appeal.py

С переопределением мерчанта:
  docker compose exec -T -e MERCHANT_USERNAME=pandapay app python manage.py shell \\
    < titanpay/basics/shell_setup_payplat_appeal.py

После запуска:
  1. Добавьте APPEAL_BOT_API_TOKEN и APPEAL_TELEGRAM_BOT_TOKEN в .env
  2. В Telegram-чате мерчанта: /init <merchant_uuid>
  3. В Telegram-чате PayPlat: /init <payplat_provider_uuid>
  4. Апелляция: фото чека + UUID pay-in в чате мерчанта
     → бот перешлёт в чат PayPlat с caption = shop_internal_id (id PayIn)
"""
import os
import uuid

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from appeals.models import AppealCounterparty, AppealCounterpartyRole
from bots.models import TGBot
from merchant.models import Merchant

MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "pandapay").strip()
MERCHANT_COUNTERPARTY_NAME = os.environ.get("MERCHANT_COUNTERPARTY_NAME", "PandaPay").strip()
PAYPLAT_PROVIDER_NAME = os.environ.get("PAYPLAT_PROVIDER_NAME", "PayPlat").strip()


def ensure_appeal_bot_user() -> str:
    user, created = User.objects.get_or_create(username="appeal_bot_user")
    if created:
        user.set_password(str(uuid.uuid4()))
        user.save()
    TGBot.objects.get_or_create(user=user)
    token, _ = Token.objects.get_or_create(user=user)
    print(f"appeal_bot_user API token: {token.key}")
    print("→ .env: APPEAL_BOT_API_TOKEN=<этот токен>")
    print("→ .env: APPEAL_TELEGRAM_BOT_TOKEN=<токен Telegram-бота апелляций>")
    return token.key


def ensure_merchant_counterparty():
    merchant = Merchant.objects.filter(user__username=MERCHANT_USERNAME).first()
    if merchant is None:
        print(f"ERROR: merchant {MERCHANT_USERNAME!r} not found")
        return None
    cp, _ = AppealCounterparty.objects.get_or_create(
        merchant=merchant,
        role=AppealCounterpartyRole.MERCHANT,
        defaults={"name": MERCHANT_COUNTERPARTY_NAME},
    )
    print(f"Merchant {cp.name}: uuid={cp.id}")
    print(f"  → в группе мерчанта: /init {cp.id}")
    return cp


def ensure_payplat_provider_counterparty():
    cp, _ = AppealCounterparty.objects.get_or_create(
        role=AppealCounterpartyRole.PROVIDER,
        psp_provider="payplat",
        defaults={"name": PAYPLAT_PROVIDER_NAME},
    )
    print(f"Provider PayPlat: uuid={cp.id}")
    print(f"  → в группе PayPlat: /init {cp.id}")
    return cp


print("=== PayPlat appeal bot setup ===")
ensure_appeal_bot_user()
ensure_merchant_counterparty()
ensure_payplat_provider_counterparty()
print("\nГотово. PayPlat create deal теперь отправляет payer=kz для KZT (см. PAYPLAT_PAYER_MAP).")
