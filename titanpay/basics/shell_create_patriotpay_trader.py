"""
Django shell: команда + трейдер PatriotPay PSP (username patriot1).

Документация: https://docs.patriotpay.club
API: POST /api/merchant/invoices (H2H Scenario A, startDeal=true)
Колбек: {PUBLIC_API_URL}/api/v1/webhooks/psp/patriotpay/

После run() в .env на сервере (секреты НЕ коммитить; пароль docs-сайта — не API-key):
  PATRIOTPAY_API_BASE=https://api.patriotpay.club
  PATRIOTPAY_API_KEY=...          # X-Identity из ЛК магазина
  PATRIOTPAY_SECRET_KEY=...       # secret из Настроек ЛК
  PATRIOTPAY_TRADER_USERNAME=patriot1
  PATRIOTPAY_PAYIN_OPTION_MAP={"C2CKZT":"TO_CARD","C2C":"TO_CARD"}
  PATRIOTPAY_PAYIN_METHOD_MAP={"C2CKZT":"","C2C":""}
  PUBLIC_API_URL=https://api.avapay.net

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_patriotpay_trader.py
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

TEAM_NAME = "PatriotPay KZT"
TRADER_USERNAME = "patriot1"
TRADER_PASSWORD = "ChangeMe_PatriotPay_1!"
TRADER_EMAIL = "patriot1@example.com"
GROUP_OWNER = "PatriotPay Virtual Drop"
TRAFFIC_NAME = "Standard"
PS_NAMES = ("C2CKZT", "C2C")


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


def run():
    print("=== PatriotPay trader setup ===")
    lang = Language.objects.first() or Language.objects.create(name="Russian")
    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        kzt = Currency.objects.create(symbol="KZT", name="Kazakhstani Tenge")
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    team, _ = TraderTeam.objects.get_or_create(
        name=TEAM_NAME, defaults={"rate_in": Decimal("5"), "rate_out": Decimal("2")}
    )
    user, created = User.objects.get_or_create(
        username=TRADER_USERNAME,
        defaults={"email": TRADER_EMAIL, "first_name": "PatriotPay", "password": TRADER_PASSWORD},
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
    for ps_name in PS_NAMES:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
        if ps is None:
            ps = PaymentSystem.objects.create(
                name=ps_name,
                currency=kzt,
                required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}},
                usdt_exchange_rate=Decimal("520"),
                expired_time_in=datetime.timedelta(minutes=15),
                expired_time_out=datetime.timedelta(minutes=10),
                confirm_time_out=datetime.timedelta(minutes=10),
                constrain_time_out=datetime.timedelta(hours=4),
            )
            print(f"  + PaymentSystem {ps.name}")
        TraderTeamRates.objects.get_or_create(
            team=team, payment_system=ps, defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")}
        )
        ensure_virtual_group(trader, kzt, ps, traffic, f"KZT {ps_name}")
    print("Done.")
    print("  1) migrate (payments 0027_patriotpay_pay_in_session)")
    print("  2) Head support: controlled_teams → PatriotPay KZT")
    print("  3) MerchantSolution: payment_system=C2CKZT, лимиты по договору")
    print("  4) .env PATRIOTPAY_API_KEY + PATRIOTPAY_SECRET_KEY из ЛК (не пароль docs)")
    print("  5) Callback URL → https://api.avapay.net/api/v1/webhooks/psp/patriotpay/")
    print("  6) пополнить patriot1 balance_usdt, иначе каскад пропускает")
    print("  7) probe: shell < basics/shell_patriotpay_probe_api.py")


run()
