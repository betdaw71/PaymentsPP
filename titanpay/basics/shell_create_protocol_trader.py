"""
Django shell: команда + трейдер Protocol PSP (username protocol1).

Лимиты мерчанта настраиваются в MerchantSolution (рекомендуется 1000–10000 KZT).
Курс: Binance P2P Halyk (см. get_binance_kzt_halyk_rate, PROTOCOL_BINANCE_PAY_TYPE).

После run() в .env:
  PROTOCOL_API_BASE=https://prot0col.com
  PROTOCOL_MERCHANT_ID=...
  PROTOCOL_SECRET_KEY=...
  PROTOCOL_TRADER_USERNAME=protocol1
  PROTOCOL_C2C_NAME=C2CKZT

Запуск:
  docker compose exec app python manage.py shell < basics/shell_create_protocol_trader.py
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
from titanpay.settings import PROTOCOL_C2C_NAME

TEAM_NAME = "Protocol Agg"
TRADER_USERNAME = "protocol1"
TRADER_PASSWORD = "ChangeMe_Protocol_1!"
TRADER_EMAIL = "protocol1@example.com"
GROUP_OWNER = "Protocol Virtual Drop"
TRAFFIC_NAME = "Standard"
PS_NAME = PROTOCOL_C2C_NAME


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
    print("=== Protocol trader setup ===")
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
    team, _ = TraderTeam.objects.get_or_create(name=TEAM_NAME, defaults={"rate_in": Decimal("5"), "rate_out": Decimal("2")})
    TraderTeamRates.objects.get_or_create(team=team, payment_system=ps, defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")})
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    user, created = User.objects.get_or_create(
        username=TRADER_USERNAME,
        defaults={"email": TRADER_EMAIL, "first_name": "Protocol", "password": TRADER_PASSWORD},
    )
    if created:
        user.set_password(TRADER_PASSWORD)
        user.save()
    trader = Trader.objects.filter(user=user).first()
    if trader is None:
        bal = Balance.objects.create(type=0, amount=Decimal("0"))
        fr = Balance.objects.create(type=1, amount=Decimal("0"))
        trader = Trader.objects.create(
            user=user, language=lang, team=team, balance_usdt=bal, frozen_balance_usdt=fr,
            currency=kzt, is_boss=True, blocked=False,
        )
        print(f"  + Trader {TRADER_USERNAME}")
    ensure_virtual_group(trader, kzt, ps, traffic, "KZT C2CKZT")
    print("Done.")
    print("  1) Head support: controlled_teams → Protocol Agg")
    print("  2) MerchantSolution: payment_system=C2CKZT, min_limit_in=1000, max_limit_in=10000")
    print("  3) PROTOCOL_* в .env, migrate, whitelist IP на стороне Protocol")
    print("  4) ExpayOne C2C — отдельно, min 10000+ (payment_system=C2C)")


if __name__ == "__main__":
    run()
else:
    print("Run: run()")
