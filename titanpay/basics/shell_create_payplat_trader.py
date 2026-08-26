"""
Django shell: команда + трейдер PayPlat PSP (username payplat1).

Документация: https://payplat.su/merchant/api/quickstart
API: POST /v1/api/deals (или /test/api/deals)
Колбек: {PUBLIC_API_URL}/api/v1/webhooks/psp/payplat/

После run() в .env (секреты НЕ коммитить):
  PAYPLAT_API_BASE=https://payplat.su/test/api
  PAYPLAT_SHOP_ID=100000100
  PAYPLAT_SECRET_KEY=100000100
  PAYPLAT_TRADER_USERNAME=payplat1
  PAYPLAT_REQUISITE_TYPE_MAP={"C2C":"c2c_ab","SBP":"sbp"}
  PUBLIC_API_URL=https://api.avapay.net

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_payplat_trader.py
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

TEAM_NAME = "PayPlat RUB"
TRADER_USERNAME = "payplat1"
TRADER_PASSWORD = "ChangeMe_PayPlat_1!"
TRADER_EMAIL = "payplat1@example.com"
GROUP_OWNER = "PayPlat Virtual Drop"
TRAFFIC_NAME = "Standard"
PS_NAMES = ("C2C", "SBP")


def ensure_virtual_group(trader, currency, payment_system, traffic, label: str):
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=payment_system, currency=currency).first()
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
        cards = PaymentDetails.objects.filter(
            group=group,
            status=1,
            sberpay_enabled=False,
            sbp_enabled=False,
            card_number__isnull=False,
        ).count()
        if cards == 0:
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
            print(f"  + virtual card for group {group.id}")
        print(f"  ~ virtual group {label} ({group.id}) status={group.status} in_active={group.in_active}")
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


def ensure_payment_system(currency, name: str):
    ps = PaymentSystem.objects.filter(name=name, currency=currency).first()
    if ps:
        return ps
    ps = PaymentSystem.objects.create(
        name=name,
        currency=currency,
        required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}},
        usdt_exchange_rate=Decimal("92"),
        expired_time_in=datetime.timedelta(minutes=15),
        expired_time_out=datetime.timedelta(minutes=10),
        confirm_time_out=datetime.timedelta(minutes=10),
        constrain_time_out=datetime.timedelta(hours=4),
        sbp_compatible=(name == "SBP"),
    )
    print(f"  + PaymentSystem {name}")
    return ps


def run():
    print("=== PayPlat trader setup ===")
    lang = Language.objects.first() or Language.objects.create(name="Russian")
    rub = Currency.objects.filter(symbol="RUB").first()
    if rub is None:
        rub = Currency.objects.create(symbol="RUB", name="Russian Ruble")
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    team, _ = TraderTeam.objects.get_or_create(
        name=TEAM_NAME, defaults={"rate_in": Decimal("5"), "rate_out": Decimal("2")}
    )
    user, created = User.objects.get_or_create(
        username=TRADER_USERNAME,
        defaults={"email": TRADER_EMAIL, "first_name": "PayPlat", "password": TRADER_PASSWORD},
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
            currency=rub,
            is_boss=True,
            blocked=False,
        )
        print(f"  + Trader {TRADER_USERNAME}")
    for ps_name in PS_NAMES:
        ps = ensure_payment_system(rub, ps_name)
        TraderTeamRates.objects.get_or_create(
            team=team, payment_system=ps, defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")}
        )
        ensure_virtual_group(trader, rub, ps, traffic, f"RUB {ps_name}")
    print("Done.")
    print("  1) migrate (payments 0022_payplat_pay_in_session)")
    print("  2) Head support: controlled_teams → PayPlat RUB")
    print("  3) MerchantSolution: payment_system=C2C/SBP RUB")
    print("  4) .env PAYPLAT_* + PUBLIC_API_URL")
    print("  5) IPN URL в ЛК PayPlat → https://api.avapay.net/api/v1/webhooks/psp/payplat/")
    print("  6) probe: shell < basics/shell_payplat_probe_api.py")


run()
