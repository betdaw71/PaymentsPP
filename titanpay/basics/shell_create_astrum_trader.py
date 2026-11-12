"""
Виртуальный трейдер Astrum для KZT pay-out (username astrum_kzt).

Группа: out_active=True, in_active=False, PS=C2CKZT.

Запуск:
  docker compose exec -T app python manage.py shell < basics/shell_create_astrum_trader.py

После run() в .env (и rebuild/restart app):
  ASTRUM_API_BASE=https://astrum.ac/api
  ASTRUM_API_KEY=...
  ASTRUM_PRIVATE_KEY=...
  ASTRUM_TRADER_USERNAME=astrum_kzt
  ASTRUM_C2C_NAME=C2CKZT
  ASTRUM_METHOD_TYPE_ID=<id из manage.py astrum_probe --methods>
  ASTRUM_METHOD_NAME_ID=   # опционально
  ASTRUM_EXPRESS=false
  LIVENESS_EXEMPT_TRADER_USERNAMES=...,astrum_kzt

Колбек у Astrum (в чате поддержки):
  https://<PUBLIC_API_URL>/api/v1/webhooks/psp/astrum/payout/
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

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
from titanpay.settings import ASTRUM_C2C_NAME, ASTRUM_TRADER_USERNAME

TEAM_NAME = "Astrum KZT Payout"
TRADER_USERNAME = ASTRUM_TRADER_USERNAME or "astrum_kzt"
TRADER_PASSWORD = "ChangeMe_Astrum_KZT_1!"
TRADER_EMAIL = "astrum_kzt@example.com"
GROUP_OWNER = "Astrum KZT virtual drop"
TRAFFIC_NAME = "Standard"
PS_NAME = ASTRUM_C2C_NAME or "C2CKZT"


def _unique_card() -> str:
    card = "4" + uuid.uuid4().hex[:15]
    return "".join(c for c in card if c.isdigit())[:16].ljust(16, "0")


def _unique_deposit_number() -> str:
    return str(uuid.uuid4().int % 10**20).zfill(20)


def ensure_payout_group(trader, currency, payment_system, traffic) -> PaymentDetailsGroup:
    group = PaymentDetailsGroup.objects.filter(
        trader=trader, payment_system=payment_system, currency=currency
    ).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner=GROUP_OWNER,
            trader=trader,
            currency=currency,
            payment_system=payment_system,
            status=1,
            amount=Decimal("9999999"),
            in_active=False,
            out_active=True,
            min_amount_out=Decimal("1000"),
            max_amount_out=Decimal("5000000"),
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
            limit_per_period=Decimal("50000000"),
        )
        group.allowed_traffic.add(traffic)
        print(f"  + group {group.id}")
    else:
        group.status = 1
        group.out_active = True
        group.in_active = False
        group.amount = max(group.amount or Decimal("0"), Decimal("9999999"))
        group.min_amount_out = Decimal("1000")
        group.max_amount_out = Decimal("5000000")
        group.deposit_number_on = False
        group.auto_live = timezone.now()
        group.save()
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ group {group.id} (out_active=True)")

    if not PaymentDetails.objects.filter(
        group=group, status=1, card_number__isnull=False, sberpay_enabled=False, sbp_enabled=False
    ).exists():
        card = _unique_card()
        PaymentDetails.objects.create(
            group=group,
            status=1,
            amount=Decimal("9999999"),
            card_number=card,
            deposit_number=_unique_deposit_number(),
            sberpay_enabled=False,
            sbp_enabled=False,
        )
        print(f"  + stub card ****{card[-4:]}")
    else:
        print("  ~ stub card already present")
    return group


def run():
    print("=== Astrum KZT pay-out trader ===")
    lang = Language.objects.first() or Language.objects.create(name="Russian")
    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        kzt = Currency.objects.create(symbol="KZT", name="Kazakhstani Tenge")
        print("  + Currency KZT")

    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
    if ps is None:
        ps = PaymentSystem.objects.create(
            name=PS_NAME,
            currency=kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}},
            usdt_exchange_rate=Decimal("520"),
            expired_time_in=datetime.timedelta(minutes=15),
            expired_time_out=datetime.timedelta(minutes=30),
            confirm_time_out=datetime.timedelta(minutes=30),
            constrain_time_out=datetime.timedelta(hours=4),
        )
        print(f"  + PaymentSystem {ps.name}")

    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    team, _ = TraderTeam.objects.get_or_create(
        name=TEAM_NAME, defaults={"rate_in": Decimal("0"), "rate_out": Decimal("2")}
    )
    TraderTeamRates.objects.get_or_create(
        team=team, payment_system=ps, defaults={"mdr_in": Decimal("0"), "mdr_out": Decimal("2.5")}
    )

    user, created = User.objects.get_or_create(
        username=TRADER_USERNAME,
        defaults={"email": TRADER_EMAIL, "first_name": "Astrum KZT"},
    )
    if created:
        user.set_password(TRADER_PASSWORD)
        user.save()
        print(f"  + user {TRADER_USERNAME} / {TRADER_PASSWORD}")
    else:
        print(f"  ~ user {TRADER_USERNAME}")

    trader = Trader.objects.filter(user=user).first()
    if trader is None:
        bal = Balance.objects.create(type=0, amount=Decimal("100000"))
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
        print(f"  + trader {trader.id}")
    else:
        changed_fields = []
        if trader.team_id != team.id:
            trader.team = team
            changed_fields.append("team")
        if trader.currency_id != kzt.id:
            trader.currency = kzt
            changed_fields.append("currency")
        if changed_fields:
            trader.save(update_fields=changed_fields)
        if trader.balance_usdt and trader.balance_usdt.amount < Decimal("1000"):
            trader.balance_usdt.amount = Decimal("100000")
            trader.balance_usdt.save(update_fields=["amount"])
            print("  + topped balance_usdt")
        print(f"  ~ trader {trader.id}")

    ensure_payout_group(trader, kzt, ps, traffic)
    print("Done. Route merchant C2CKZT out limits so astrum_kzt can match.")
    print("Then: python manage.py astrum_probe --info --balance --methods")


run()
