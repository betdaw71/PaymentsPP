"""
Django shell: мерчант Alemkredit — KZT трансгран (C2CKZT), pay-in 8%.

Создаёт пользователя, Merchant, MerchantSolution (STD + FTD), API-креды.
Роутинг на PSP (BotonPay / Bitzone / PayMap) общий для C2CKZT — отдельно не настраивается.

Запуск на сервере:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_alemkredit_merchant.py

Или в shell:
  exec(open("basics/shell_create_alemkredit_merchant.py").read())
  run()

Env: ALEMKREDIT_MERCHANT_USERNAME, ALEMKREDIT_MERCHANT_PASSWORD, ALEMKREDIT_MDR_IN (default 8).
"""
from __future__ import annotations

import datetime
import os
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.authtoken.models import Token

from basics.models import Balance, Currency, Language, PaymentSystem, TrafficType
from merchant.models import Merchant, MerchantSolution
from payments.models import APIKeys
from trade.models import Address

MERCHANT_USERNAME = os.environ.get("ALEMKREDIT_MERCHANT_USERNAME", "alemkredit")
DEFAULT_PASSWORD = os.environ.get("ALEMKREDIT_MERCHANT_PASSWORD", "Alemkredit_2026!")
PS_NAME = "C2CKZT"
TRAFFIC_NAME = "Standard"
MDR_IN = Decimal(os.environ.get("ALEMKREDIT_MDR_IN", "8"))
MDR_OUT = Decimal(os.environ.get("ALEMKREDIT_MDR_OUT", "8"))

LIMITS = {
    "min_limit_in": Decimal(os.environ.get("ALEMKREDIT_MIN_IN", "1000")),
    "max_limit_in": Decimal(os.environ.get("ALEMKREDIT_MAX_IN", "1000000")),
    "min_limit_out": Decimal(os.environ.get("ALEMKREDIT_MIN_OUT", "1000")),
    "max_limit_out": Decimal(os.environ.get("ALEMKREDIT_MAX_OUT", "1000000")),
}


def _deposit_address(username: str) -> str:
    try:
        from basics.utils import generate_address

        address = generate_address()
        if address:
            return address
    except Exception as exc:
        print(f"  ! crypto service unavailable ({exc}); placeholder address")
    return f"alemkredit_{username}_{uuid.uuid4().hex[:16]}"


@transaction.atomic
def run(password: str = DEFAULT_PASSWORD) -> dict:
    print("=" * 60)
    print(f"Alemkredit — KZT / {PS_NAME} (трансгран, mdr_in {MDR_IN}%)")
    print("=" * 60)

    language, _ = Language.objects.get_or_create(name="English")
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    currency = Currency.objects.filter(symbol="KZT").first()
    if currency is None:
        raise SystemExit("Currency KZT not found")
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=currency).first()
    if ps is None:
        raise SystemExit(
            f"PaymentSystem {PS_NAME} not found — создайте через shell_create_melbet_test_merchant.py "
            "или shell_create_botonpay_trader.py"
        )
    print(f"  ~ PaymentSystem {ps.name} ({ps.id})")

    email = f"{MERCHANT_USERNAME}@merchant.local"
    user, user_created = User.objects.get_or_create(
        username=MERCHANT_USERNAME,
        defaults={"email": email, "first_name": "Alemkredit"},
    )
    if user_created:
        user.set_password(password)
        user.save()
        print(f"  + User {MERCHANT_USERNAME}")
    else:
        user.set_password(password)
        user.save(update_fields=["password"])
        print(f"  ~ User {MERCHANT_USERNAME} (password reset)")

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
            telegram="@alemkredit",
            phone="+77000000000",
        )
        Address.objects.create(balance=balance, address_public=_deposit_address(MERCHANT_USERNAME))
        merchant_created = True
        print(f"  + Merchant {merchant.id}")

    if not merchant.payment_systems.filter(pk=ps.pk).exists():
        merchant.payment_systems.add(ps)
        print(f"  + linked PS {PS_NAME}")
    else:
        print(f"  ~ PS {PS_NAME} already on merchant")

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
        print(f"  {tag} MerchantSolution ftd={ftd} mdr_in={sol.mdr_in}%")

    if user_created or merchant_created:
        api_key = APIKeys.create(merchant=merchant)
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
    else:
        api_key = APIKeys.create(merchant=merchant)
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        print("  ~ API keys re-issued")

    result = {
        "merchant_id": str(merchant.id),
        "username": MERCHANT_USERNAME,
        "password": password,
        "api_token": token.key,
        "private_key": str(api_key.private_key),
        "payment_system": PS_NAME,
        "mdr_in": str(MDR_IN),
    }

    print("\n" + "=" * 60)
    print("ГОТОВО — Alemkredit")
    print("=" * 60)
    print(f"  Merchant ID:  {result['merchant_id']}")
    print(f"  Логин кабинета: {result['username']}")
    print(f"  Пароль:       {result['password']}")
    print(f"  API Token:    {result['api_token']}")
    print(f"  Private key:  {result['private_key']}")
    print(f"  Pay-in MDR:   {MDR_IN}%")
    print(f"  Payment PS:   {PS_NAME}")
    print(f"  Limits in:    {LIMITS['min_limit_in']} – {LIMITS['max_limit_in']} KZT")
    print("\nH2H: POST https://api.avapay.net/api/v1/payments/in/h2h/")
    print("  currency=KZT  payment_system=C2CKZT  ftd=false")
    print(
        f"\nПроверка: python manage.py diagnose_routing {MERCHANT_USERNAME} "
        f"--ps {PS_NAME} --amount 5000 --ftd false"
    )
    return result


if __name__ == "__main__":
    run()
else:
    print("Запустите: run()")
