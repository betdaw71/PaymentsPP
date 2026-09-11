# Скрипт: создать заявку на вывод мерчанту (WithdrawalRequest)
# Запуск на сервере:
#   docker compose exec app python manage.py shell < basics/create_merchant_withdrawal_request.py
# или после деплоя команды:
#   docker compose exec app python manage.py create_merchant_withdrawal aggrepay 5000 --address 'T...'
#   docker compose exec app python manage.py create_merchant_withdrawal aggrepay 5000 --reuse-last-address

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "titanpay.settings")

import django
django.setup()

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction

from trade.models import WithdrawalRequest

# === параметры ===
MERCHANT_USERNAME = "aggrepay"
AMOUNT = Decimal("5000")
# Укажите USDT-адрес. Если пусто — берётся address_to из последней заявки мерчанта.
ADDRESS = ""
DRY_RUN = False
# =================


def create_merchant_withdrawal(username: str, amount: Decimal, address: str = "", dry_run: bool = False):
    print("ЗАЯВКА НА ВЫВОД МЕРЧАНТА")
    print(f"   Мерчант: {username}")
    print(f"   Сумма:   {amount}")
    print("-" * 50)

    try:
        user = User.objects.select_related("merchant", "merchant__balance").get(username=username)
    except User.DoesNotExist:
        print(f"Пользователь {username!r} не найден")
        return None

    if not hasattr(user, "merchant") or user.merchant is None:
        print(f"У пользователя {username!r} нет профиля Merchant")
        return None

    merchant = user.merchant
    balance = merchant.balance
    print(f"Найден мерчант: {username}")
    print(f"   Текущий баланс: {balance.amount}")

    address = (address or "").strip()
    if not address:
        last = (
            WithdrawalRequest.objects.filter(from_user=user)
            .exclude(address_to="")
            .order_by("-date")
            .first()
        )
        if last is None:
            print("Нет прошлого адреса — задайте ADDRESS в скрипте")
            return None
        address = last.address_to.strip()
        print(f"   Адрес из заявки {last.id}: {address}")
    else:
        print(f"   Адрес: {address}")

    if len(address) > 50:
        print(f"Адрес длиннее 50 символов ({len(address)})")
        return None

    if balance.amount < amount:
        print(f"Недостаточно средств: нужно {amount}, доступно {balance.amount}")
        return None

    if dry_run:
        print("DRY_RUN: заявка не создана")
        return None

    try:
        with transaction.atomic():
            wr = WithdrawalRequest.create(
                amount=amount,
                _from=balance,
                address_to=address,
                from_user=user,
            )
    except ValidationError as e:
        print(f"Ошибка валидации: {e}")
        return None

    balance.refresh_from_db()
    print(f"Заявка создана: id={wr.id}")
    print(f"   status={wr.status} amount={wr.amount}")
    print(f"   Новый баланс: {balance.amount}")
    return wr


create_merchant_withdrawal(MERCHANT_USERNAME, amount, ADDRESS, DRY_RUN)
