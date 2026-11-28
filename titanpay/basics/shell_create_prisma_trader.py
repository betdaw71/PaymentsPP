"""PrismaPay/Spyder trader prisma1 + virtual KGS groups (C2CKGS / PHONEKGS / QRKGS).

Docs: https://prismapay.software (Spyder merchant API).
  PRISMA_API_BASE=https://prismapay.software
  PRISMA_API_TOKEN=...
  PRISMA_CALLBACK_SECRET=...
  Callback URL: {PUBLIC_API_URL}/api/v1/webhooks/psp/prisma/

  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_prisma_trader.py
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
from merchant.kzt_settlement import C2C_KGS_PS_NAME, KGS_PS_NAME, PHONE_KGS_PS_NAME
from payments.prisma_client import prisma_trader_username

TEAM_NAME = "Prisma KGS"
TRAFFIC_NAME = "Standard"
DEFAULT_RATE = Decimal("87")
DEFAULT_MDR_IN = Decimal("7")

PS_SPECS = (
    (
        KGS_PS_NAME,
        {
            "qr_payload": {"regex": r".+", "pattern": "QR payload / photo URL"},
            "phone": {"regex": r"^\+\d{10,15}$", "pattern": "Phone +996…"},
        },
    ),
    (
        C2C_KGS_PS_NAME,
        {
            "card_number": {"regex": r"^\d{16}$", "pattern": "Card number"},
            "bank_name": {"regex": r".+", "pattern": "Bank name"},
        },
    ),
    (
        PHONE_KGS_PS_NAME,
        {
            "phone": {"regex": r"^\+\d{10,15}$", "pattern": "Phone +996…"},
            "bank_name": {"regex": r".+", "pattern": "Bank name"},
        },
    ),
)


def ensure_currency() -> Currency:
    cur = Currency.objects.filter(symbol="KGS").first()
    if cur is None:
        cur = Currency.objects.create(symbol="KGS", name="Kyrgyz som")
        print(f"  + Currency KGS")
    else:
        print(f"  ~ Currency KGS")
    return cur


def ensure_ps(currency: Currency, name: str, required_fields: dict) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=name, currency=currency).first()
    if ps is None:
        ps = PaymentSystem.objects.create(
            name=name,
            currency=currency,
            required_fields=required_fields or {},
            usdt_exchange_rate=DEFAULT_RATE,
            expired_time_in=datetime.timedelta(minutes=15),
            expired_time_out=datetime.timedelta(minutes=10),
            confirm_time_out=datetime.timedelta(minutes=10),
            constrain_time_out=datetime.timedelta(hours=4),
            in_on=True,
            out_on=False,
            sbp_compatible=False,
        )
        print(f"  + PaymentSystem {name}")
        return ps
    fields: list[str] = []
    if not ps.in_on:
        ps.in_on = True
        fields.append("in_on")
    if required_fields and ps.required_fields != required_fields:
        ps.required_fields = required_fields
        fields.append("required_fields")
    if fields:
        ps.save(update_fields=fields)
        print(f"  ~ PaymentSystem {name} updated {fields}")
    else:
        print(f"  ~ PaymentSystem {name}")
    return ps


def ensure_virtual_group(trader, currency, payment_system, traffic, label: str) -> None:
    group = PaymentDetailsGroup.objects.filter(
        trader=trader, payment_system=payment_system, currency=currency
    ).first()
    if group:
        changed = False
        if group.status != 1 or not group.in_active:
            group.status, group.in_active = 1, True
            changed = True
        if group.amount != Decimal("999999"):
            group.amount = Decimal("999999")
            changed = True
        if changed:
            group.save()
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ group {label} {group.id} in_active={group.in_active}")
    else:
        group = PaymentDetailsGroup.objects.create(
            owner=f"Prisma Virtual Drop {label}",
            trader=trader,
            currency=currency,
            payment_system=payment_system,
            status=1,
            amount=Decimal("999999"),
            in_active=True,
            out_active=False,
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
            current_volume=Decimal("0"),
        )
        group.allowed_traffic.add(traffic)
        print(f"  + group {label} {group.id}")

    if not PaymentDetails.objects.filter(group=group, status=1).exists():
        card = "".join(c for c in ("4" + uuid.uuid4().hex) if c.isdigit())[:16].ljust(16, "0")
        PaymentDetails.objects.create(
            group=group,
            status=1,
            amount=Decimal("999999"),
            card_number=card,
            deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
            sberpay_enabled=False,
            sbp_enabled=False,
        )
        print(f"    + virtual card ({label})")


print("=== Prisma trader setup (KGS) ===")
username = prisma_trader_username()
lang = Language.objects.first() or Language.objects.create(name="Russian")
currency = ensure_currency()
traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
team, _ = TraderTeam.objects.get_or_create(
    name=TEAM_NAME,
    defaults={"rate_in": DEFAULT_MDR_IN, "rate_out": Decimal("2")},
)
user, created = User.objects.get_or_create(
    username=username,
    defaults={"email": f"{username}@example.com", "first_name": "Prisma"},
)
if created:
    user.set_password("ChangeMe_Prisma_1!")
    user.save()
    print(f"  + User {username}")
else:
    print(f"  ~ User {username}")

trader = Trader.objects.filter(user=user).first()
if trader is None:
    trader = Trader.objects.create(
        user=user,
        language=lang,
        team=team,
        currency=currency,
        is_boss=True,
        blocked=False,
        balance_usdt=Balance.objects.create(type=0, amount=Decimal("50000")),
        frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
    )
    print(f"  + Trader {username}")
else:
    if trader.blocked:
        trader.blocked = False
        trader.save(update_fields=["blocked"])
    if trader.team_id != team.id:
        trader.team = team
        trader.save(update_fields=["team"])
    print(f"  ~ Trader {username}")

for ps_name, required in PS_SPECS:
    ps = ensure_ps(currency, ps_name, required)
    if trader.team_id:
        TraderTeamRates.objects.get_or_create(
            team=trader.team,
            payment_system=ps,
            defaults={"mdr_in": DEFAULT_MDR_IN, "mdr_out": Decimal("2.5")},
        )
    ensure_virtual_group(trader, currency, ps, traffic, ps_name)

print(
    "Done. migrate 0030 + .env PRISMA_* + callback URL in Prisma profile "
    f"→ {{PUBLIC_API_URL}}/api/v1/webhooks/psp/prisma/"
)
print("Then: shell_setup_melbet_kgs_prisma.py for Melbet solutions / method_map.")
