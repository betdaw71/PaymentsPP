"""Nexus trader nexus1 + virtual C2CKZT group. Docs: https://az26juuc.xyz/docs
  NEXUS_API_BASE=https://az26juuc.xyz
  NEXUS_API_TOKEN=...
  NEXUS_CALLBACK_SECRET=...
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_nexus_trader.py
"""
from decimal import Decimal
import datetime, uuid
from django.contrib.auth.models import User
from django.utils import timezone
from basics.models import (
    Balance, Currency, Language, PaymentDetails, PaymentDetailsGroup,
    PaymentSystem, Trader, TraderTeam, TraderTeamRates, TrafficType,
)

TEAM_NAME, TRADER_USERNAME = "Nexus KZT", "nexus1"
PS_NAME, TRAFFIC_NAME = "C2CKZT", "Standard"


def ensure_virtual_group(trader, currency, payment_system, traffic, label):
    group = PaymentDetailsGroup.objects.filter(
        trader=trader, payment_system=payment_system, currency=currency
    ).first()
    if group:
        if group.status != 1 or not group.in_active:
            group.status, group.in_active = 1, True
            group.save()
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ group {label} {group.id} in_active={group.in_active}")
        return
    group = PaymentDetailsGroup.objects.create(
        owner=f"Nexus Virtual Drop {label}", trader=trader, currency=currency,
        payment_system=payment_system, status=1, amount=Decimal("999999"),
        in_active=True, out_active=False, work_type="by_card",
        deposit_number_on=False, auto_live=timezone.now(),
    )
    group.allowed_traffic.add(traffic)
    card = "".join(c for c in ("4" + uuid.uuid4().hex) if c.isdigit())[:16].ljust(16, "0")
    PaymentDetails.objects.create(
        group=group, status=1, amount=Decimal("999999"), card_number=card,
        deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
        sberpay_enabled=False, sbp_enabled=False,
    )
    print(f"  + group {label} {group.id}")


print("=== Nexus trader setup ===")
lang = Language.objects.first() or Language.objects.create(name="Russian")
kzt = Currency.objects.filter(symbol="KZT").first()
if kzt is None:
    raise SystemExit("Currency KZT not found")
ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
if ps is None:
    ps = PaymentSystem.objects.create(
        name=PS_NAME, currency=kzt,
        required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}},
        usdt_exchange_rate=Decimal("520"),
        expired_time_in=datetime.timedelta(minutes=15),
        expired_time_out=datetime.timedelta(minutes=10),
        confirm_time_out=datetime.timedelta(minutes=10),
        constrain_time_out=datetime.timedelta(hours=4),
    )
team, _ = TraderTeam.objects.get_or_create(name=TEAM_NAME, defaults={"rate_in": Decimal("4.70"), "rate_out": Decimal("2")})
TraderTeamRates.objects.get_or_create(team=team, payment_system=ps, defaults={"mdr_in": Decimal("4.70"), "mdr_out": Decimal("2.5")})
traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
user, created = User.objects.get_or_create(username=TRADER_USERNAME, defaults={"email": "nexus1@example.com", "first_name": "Nexus"})
if created:
    user.set_password("ChangeMe_Nexus_1!")
    user.save()
trader = Trader.objects.filter(user=user).first()
if trader is None:
    trader = Trader.objects.create(
        user=user, language=lang, team=team, currency=kzt, is_boss=True, blocked=False,
        balance_usdt=Balance.objects.create(type=0, amount=Decimal("50000")),
        frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
    )
    print(f"  + Trader {TRADER_USERNAME}")
else:
    if trader.blocked:
        trader.blocked = False
        trader.save(update_fields=["blocked"])
ensure_virtual_group(trader, kzt, ps, traffic, "KZT C2CKZT")
print("Done. migrate 0029 + .env NEXUS_* + callback URL in Nexus profile.")
