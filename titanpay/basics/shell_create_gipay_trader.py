"""
Django shell: команда + трейдер GiPay PSP (username gipay1).

Документация: https://documenter.getpostman.com/view/13931884/2sAYQdipUu
API: Aggrepay v2 (POST /api/v2/payments), аналогично Protocol.
Колбек: {PUBLIC_API_URL}/api/v1/webhooks/psp/gipay/

После run() в .env (секреты НЕ коммитить):
  GIPAY_API_BASE=https://gipay.org
  GIPAY_MERCHANT_ID=M_ELKSZ3Z9
  GIPAY_SECRET_KEY=...
  GIPAY_API_KEY=...
  GIPAY_TRADER_USERNAME=gipay1
  GIPAY_PAYIN_METHOD=kztg

Запуск:
  docker compose exec -T app python manage.py shell < basics/shell_create_gipay_trader.py
"""
from decimal import Decimal
import datetime
import uuid

from django.contrib.auth.models import User
from django.utils import timezone

from basics.models import (
    Balance,
    Currency,
    Language,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeam,
    TraderTeamRates,
    TrafficType,
)

TEAM_NAME = "GiPay KZT"
TRADER_USERNAME = "gipay1"
TRADER_PASSWORD = "ChangeMe_GiPay_1!"
TRADER_EMAIL = "gipay1@example.com"
GROUP_OWNER = "GiPay Virtual Drop"
TRAFFIC_NAME = "Standard"
PS_NAME = "C2CKZT"


def ensure_virtual_group(trader, currency, payment_system, traffic, label: str):
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=payment_system, currency=currency).first()
    if group:
        if group.status != 1 or not group.in_active:
            group.status = 1
            group.in_active = True
            group.amount = Decimal("999999")
            group.save(update_fields=["status", "in_active", "amount"])
        print(f"  ~ virtual group {label} ({group.id})")
        return
    group = PaymentDetailsGroup.objects.create(
        owner=f"{GROUP_OWNER} {label}",
        trader=trader,
        currency=currency,
        payment_system=payment_system,
        status=1,
        amount=Decimal("999999"),
        in_active=True,
        out_active=False,
        min_amount_out=Decimal("1000"),
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
    print(f"  + Virtual group {label} ({group.id})")


def run():
    print("=== GiPay trader setup ===")
    lang = Language.objects.first() or Language.objects.create(name="Russian")
    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        kzt = Currency.objects.create(symbol="KZT", name="Kazakhstani Tenge")
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
    if ps is None:
        ps = PaymentSystem.objects.create(
            name=PS_NAME,
            currency=kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}},
            usdt_exchange_rate=Decimal("520"),
            expired_time_in=datetime.timedelta(minutes=15),
            expired_time_out=datetime.timedelta(minutes=10),
            confirm_time_out=datetime.timedelta(minutes=10),
            constrain_time_out=datetime.timedelta(hours=4),
        )
        print(f"  + PaymentSystem {ps.name}")
    team, _ = TraderTeam.objects.get_or_create(
        name=TEAM_NAME, defaults={"rate_in": Decimal("5"), "rate_out": Decimal("2")}
    )
    TraderTeamRates.objects.get_or_create(
        team=team, payment_system=ps, defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")}
    )
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    user, created = User.objects.get_or_create(
        username=TRADER_USERNAME,
        defaults={"email": TRADER_EMAIL, "first_name": "GiPay", "password": TRADER_PASSWORD},
    )
    if created:
        user.set_password(TRADER_PASSWORD)
        user.save()
    trader = Trader.objects.filter(user=user).first()
    if trader is None:
        bal = Balance.objects.create(type=0, amount=Decimal("0"))
        fr = Balance.objects.create(type=1, amount=Decimal("0"))
        trader = Trader.objects.create(
            user=user,
            language=lang,
            team=team,
            balance_usdt=bal,
            frozen_balance_usdt=fr,
            currency=kzt,
            is_boss=True,
            blocked=False,
        )
        print(f"  + Trader {TRADER_USERNAME}")
    ensure_virtual_group(trader, kzt, ps, traffic, "KZT C2CKZT")
    print("Done.")
    print("  1) migrate (payments 0020_gipay_pay_in_session)")
    print("  2) Head support: controlled_teams → GiPay KZT")
    print("  3) MerchantSolution: payment_system=C2CKZT, лимиты по договору")
    print("  4) .env GIPAY_* + PUBLIC_API_URL; whitelist IP в ЛК merchant.gipay.net")
    print("  5) Callback URL → https://api.avapay.net/api/v1/webhooks/psp/gipay/")


run()
