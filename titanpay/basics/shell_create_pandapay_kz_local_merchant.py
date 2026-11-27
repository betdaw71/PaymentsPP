"""Django shell: мерчант pandapay_kz_local — C2C KZT, mdr_in 8.5%, курс xe+5.

Курс: без ключа в XE_KZT_MARKUP_BY_MERCHANT → дефолт PS / глобал = xe+5 (1.05).
Не копировать pandapay/aggrepay (у них 1.04).

  # создать / обновить
  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_create_pandapay_kz_local_merchant.py

Env:
  PANDAPAY_KZ_LOCAL_USERNAME (default pandapay_kz_local)
  PANDAPAY_KZ_LOCAL_PASSWORD
  PANDAPAY_KZ_LOCAL_MDR_IN (default 8.5)
  PANDAPAY_KZ_LOCAL_PS (default C2C)
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.authtoken.models import Token

from basics.models import Balance, Currency, Language, PaymentSystem, TrafficType
from basics.utils import xe_kzt_markup_for_merchant
from merchant.models import Merchant, MerchantSolution
from payments.models import APIKeys
from trade.models import Address

MERCHANT_USERNAME = os.environ.get("PANDAPAY_KZ_LOCAL_USERNAME", "pandapay_kz_local").strip()
DEFAULT_PASSWORD = os.environ.get(
    "PANDAPAY_KZ_LOCAL_PASSWORD", "PandapayKZ_Local_2026!"
)
PS_NAME = (os.environ.get("PANDAPAY_KZ_LOCAL_PS") or "C2C").strip()
TRAFFIC_NAME = "Standard"
MDR_IN = Decimal(os.environ.get("PANDAPAY_KZ_LOCAL_MDR_IN", "8.5"))
MDR_OUT = Decimal(os.environ.get("PANDAPAY_KZ_LOCAL_MDR_OUT", "8.5"))

LIMITS = {
    "min_limit_in": Decimal(os.environ.get("PANDAPAY_KZ_LOCAL_MIN_IN", "1000")),
    "max_limit_in": Decimal(os.environ.get("PANDAPAY_KZ_LOCAL_MAX_IN", "1000000")),
    "min_limit_out": Decimal(os.environ.get("PANDAPAY_KZ_LOCAL_MIN_OUT", "1000")),
    "max_limit_out": Decimal(os.environ.get("PANDAPAY_KZ_LOCAL_MAX_OUT", "1000000")),
}


def _deposit_address(username: str) -> str:
    try:
        from basics.utils import generate_address

        address = generate_address()
        if address:
            return address
    except Exception as exc:
        print(f"  ! crypto service unavailable ({exc}); placeholder address")
    return f"pandapay_kz_local_{username}_{uuid.uuid4().hex[:16]}"


@transaction.atomic
def run(password: str = DEFAULT_PASSWORD) -> dict:
    print("=" * 60)
    print(f"{MERCHANT_USERNAME} — KZT / {PS_NAME}  mdr_in={MDR_IN}%  xe+5")
    print("=" * 60)

    language, _ = Language.objects.get_or_create(name="English")
    traffic, _ = TrafficType.objects.get_or_create(
        name=TRAFFIC_NAME, defaults={"risk_level": 0}
    )
    currency = Currency.objects.filter(symbol="KZT").first()
    if currency is None:
        raise SystemExit("Currency KZT not found")

    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=currency).first()
    if ps is None:
        # fallback: C2C без фильтра валюты (как у части инсталляций)
        ps = PaymentSystem.objects.filter(name=PS_NAME).first()
    if ps is None:
        raise SystemExit(f"PaymentSystem {PS_NAME} not found")
    print(
        f"  ~ PaymentSystem {ps.name} "
        f"currency={getattr(ps.currency, 'symbol', None)} rate={ps.usdt_exchange_rate}"
    )

    email = f"{MERCHANT_USERNAME}@merchant.local"
    user, user_created = User.objects.get_or_create(
        username=MERCHANT_USERNAME,
        defaults={"email": email, "first_name": "PandaPay KZ Local"},
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
            telegram="@pandapay_kz_local",
            phone="+77000000010",
        )
        Address.objects.create(
            balance=balance, address_public=_deposit_address(MERCHANT_USERNAME)
        )
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
            sol.traffic = traffic
            for k, v in LIMITS.items():
                setattr(sol, k, v)
            sol.save()
        tag = "+" if created else "~"
        print(f"  {tag} MerchantSolution ftd={ftd} mdr_in={sol.mdr_in}% status={sol.status}")

    api_key = APIKeys.create(merchant=merchant)
    Token.objects.filter(user=user).delete()
    token = Token.objects.create(user=user)
    if not (user_created or merchant_created):
        print("  ~ API keys re-issued")

    markup = xe_kzt_markup_for_merchant(MERCHANT_USERNAME, PS_NAME)
    xe_map = getattr(settings, "XE_KZT_MARKUP_BY_MERCHANT", "") or ""

    result = {
        "merchant_id": str(merchant.id),
        "username": MERCHANT_USERNAME,
        "password": password,
        "api_token": token.key,
        "private_key": str(api_key.private_key),
        "payment_system": PS_NAME,
        "mdr_in": str(MDR_IN),
        "xe_markup": str(markup),
    }

    print("\n" + "=" * 60)
    print("ГОТОВО — pandapay_kz_local")
    print("=" * 60)
    print(f"  Merchant ID:  {result['merchant_id']}")
    print(f"  Логин:        {result['username']}")
    print(f"  Пароль:       {result['password']}")
    print(f"  API Token:    {result['api_token']}")
    print(f"  Private key:  {result['private_key']}")
    print(f"  Pay-in MDR:   {MDR_IN}%")
    print(f"  Payment PS:   {PS_NAME}")
    print(f"  Limits in:    {LIMITS['min_limit_in']} – {LIMITS['max_limit_in']} KZT")
    print(f"  XE markup:    {markup}  (1.05 = xe+5)")
    print(f"  XE_KZT_MARKUP_BY_MERCHANT env: {xe_map}")
    if markup != Decimal("1.05"):
        print(
            "  ! ожидался xe+5 (1.05). Не добавляйте этого мерчанта в "
            'XE_KZT_MARKUP_BY_MERCHANT с 1.04 — уберите ключ или поставьте "1.05".'
        )
    else:
        print("  ✓ курс xe+5 (дефолт / без override)")
    print("\nH2H: POST https://api.avapay.net/api/v1/payments/in/h2h/")
    print(f"  currency=KZT  payment_system={PS_NAME}  ftd=false")
    print(
        f"\nПроверка: python manage.py diagnose_routing {MERCHANT_USERNAME} "
        f"--ps {PS_NAME} --amount 5000 --ftd false"
    )
    return result


run()
