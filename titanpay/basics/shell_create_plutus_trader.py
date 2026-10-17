"""
Django shell: трейдер PlutusPay PSP (username plutus1) + виртуальные группы C2C и C2CKZT (KZT).

Документация: https://plutuspay.top/docs
Webhook: {PUBLIC_API_URL}/api/v1/webhooks/psp/plutus/

После run() в .env:
  PLUTUS_API_BASE=https://plutuspay.top
  PLUTUS_API_KEY=<ключ из ЛК Plutus>
  PLUTUS_TRADER_USERNAME=plutus1
  PLUTUS_PAYMETHOD_MAP={"C2C":"c2c","C2CKZT":"c2c"}
  PUBLIC_API_URL=https://api.avapay.net

В кабинете Plutus укажите callback (если требуется глобально):
  https://api.avapay.net/api/v1/webhooks/psp/plutus/

Sandbox-ключ (тест): th_sandbox_00000000000000000000000000000000

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_plutus_trader.py
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
from titanpay.settings import C2C_NAME

TEAM_NAME = "Plutus Agg"
TRADER_USERNAME = "plutus1"
TRADER_PASSWORD = "ChangeMe_Plutus_1!"
TRADER_EMAIL = "plutus1@example.com"
GROUP_OWNER = "Plutus Virtual Drop"
TRAFFIC_NAME = "Standard"
PS_NAMES = (C2C_NAME, "C2CKZT")
PSP_FLOAT_USDT = Decimal("50000")


def ensure_virtual_group(trader, currency, payment_system, traffic, label: str):
    group = PaymentDetailsGroup.objects.filter(
        trader=trader, payment_system=payment_system, currency=currency
    ).first()
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
        print(f"  ~ virtual group {label} ({group.id})")
        return group
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
    print(f"  + virtual group {label} ({group.id})")
    return group


def ensure_psp_float(trader):
    bal = trader.balance_usdt
    if bal.amount < PSP_FLOAT_USDT:
        bal.amount = PSP_FLOAT_USDT
        bal.save(update_fields=["amount"])
        print(f"  + balance_usdt topped up to {PSP_FLOAT_USDT}")
    else:
        print(f"  ~ balance_usdt {bal.amount} (ok)")


def ensure_payment_system(name: str, kzt):
    ps = PaymentSystem.objects.filter(name=name, currency=kzt).first()
    if ps is None:
        ps = PaymentSystem.objects.filter(name=name).first()
    if ps is None:
        ps = PaymentSystem.objects.create(
            name=name,
            currency=kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}},
            usdt_exchange_rate=Decimal("520"),
            expired_time_in=datetime.timedelta(minutes=15),
            expired_time_out=datetime.timedelta(minutes=10),
            confirm_time_out=datetime.timedelta(minutes=10),
            constrain_time_out=datetime.timedelta(hours=4),
        )
        print(f"  + PaymentSystem {ps.name}")
    else:
        print(f"  ~ PaymentSystem {ps.name} ({ps.id}) currency={ps.currency.symbol}")
    return ps


def run():
    print("=== PlutusPay trader setup ===")
    lang = Language.objects.first() or Language.objects.create(name="Russian")
    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        kzt = Currency.objects.create(symbol="KZT", name="Kazakhstani Tenge")

    team, _ = TraderTeam.objects.get_or_create(
        name=TEAM_NAME, defaults={"rate_in": Decimal("5"), "rate_out": Decimal("2")}
    )
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    user, created = User.objects.get_or_create(
        username=TRADER_USERNAME,
        defaults={"email": TRADER_EMAIL, "first_name": "Plutus", "password": TRADER_PASSWORD},
    )
    if created:
        user.set_password(TRADER_PASSWORD)
        user.save()
        print(f"  + User {TRADER_USERNAME}")
    else:
        print(f"  ~ User {TRADER_USERNAME}")

    trader = Trader.objects.filter(user=user).first()
    if trader is None:
        bal = Balance.objects.create(type=0, amount=PSP_FLOAT_USDT)
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
    else:
        if trader.team_id != team.id:
            trader.team = team
            trader.save(update_fields=["team"])
        ensure_psp_float(trader)
        print(f"  ~ Trader {TRADER_USERNAME}")

    for ps_name in PS_NAMES:
        ps = ensure_payment_system(ps_name, kzt)
        TraderTeamRates.objects.get_or_create(
            team=team,
            payment_system=ps,
            defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")},
        )
        ensure_virtual_group(trader, kzt, ps, traffic, f"KZT {ps_name}")

    print("")
    print("Done.")
    print("  1) migrate: docker compose exec app python manage.py migrate payments")
    print("  2) Head support: controlled_teams → «Plutus Agg»")
    print("  3) MerchantSolution: C2C и C2CKZT, currency KZT")
    print("  4) .env PLUTUS_API_KEY + callback в ЛК Plutus")
    print("  5) Webhook: {PUBLIC_API_URL}/api/v1/webhooks/psp/plutus/")
    print(f"  6) Trader login: {TRADER_USERNAME} / {TRADER_PASSWORD} (смените пароль)")


run()
