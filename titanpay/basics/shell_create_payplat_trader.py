"""
Django shell: команда + трейдер PayPlat PSP (username payplat1).

Виртуальные группы (все KZT):
  - C2C (KZT)        — создаётся, по умолчанию неактивна
  - C2CKZT (KZT)     — создаётся, по умолчанию неактивна
  - C2CKZTTEST (KZT) — единственная активная (для тестов)

Документация: https://payplat.su/merchant/api/quickstart
Колбек: {PUBLIC_API_URL}/api/v1/webhooks/psp/payplat/

После run() в .env:
  PAYPLAT_API_BASE=https://payplat.su/test/api
  PAYPLAT_SHOP_ID=100000100
  PAYPLAT_SECRET_KEY=100000100
  PAYPLAT_TRADER_USERNAME=payplat1
  PAYPLAT_REQUISITE_TYPE_MAP={"C2C":"c2c_ab","C2CKZT":"c2c_ab","C2CKZTTEST":"c2c_ab"}
  PUBLIC_API_URL=https://api.avapay.net

Тестовый роутинг мерчанта:
  shell < titanpay/basics/shell_setup_payplat_c2ckzttest_routing.py

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
from payments.payplat_client import payplat_trader_username

TEAM_NAME = "PayPlat Agg"
TRADER_USERNAME = payplat_trader_username()
TRADER_PASSWORD = "ChangeMe_PayPlat_1!"
TRADER_EMAIL = "payplat1@example.com"
GROUP_OWNER = "PayPlat Virtual Drop"
TRAFFIC_NAME = "Standard"
ACTIVE_TEST_PS = "C2CKZTTEST"
# (payment_system_name, currency_symbol, in_active)
PS_ROWS = (
    ("C2C", "KZT", False),
    ("C2CKZT", "KZT", False),
    ("C2CKZTTEST", "KZT", True),
)


def ensure_currency(symbol: str, name: str) -> Currency:
    cur = Currency.objects.filter(symbol=symbol).first()
    if cur is None:
        cur = Currency.objects.create(symbol=symbol, name=name)
        print(f"  + Currency {symbol}")
    return cur


def ensure_payment_system(currency: Currency, name: str) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=name, currency=currency).first()
    if ps:
        return ps
    ps = PaymentSystem.objects.create(
        name=name,
        currency=currency,
        required_fields={
            "card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"},
            "owner": {"regex": r"^.+$", "pattern": "Card holder"},
            "bank": {"regex": r"^.+$", "pattern": "Bank"},
        },
        usdt_exchange_rate=Decimal("520") if currency.symbol == "KZT" else Decimal("92"),
        expired_time_in=datetime.timedelta(minutes=15),
        expired_time_out=datetime.timedelta(minutes=10),
        confirm_time_out=datetime.timedelta(minutes=10),
        constrain_time_out=datetime.timedelta(hours=4),
        in_on=True,
        out_on=False,
        sbp_compatible=False,
    )
    print(f"  + PaymentSystem {name} ({currency.symbol})")
    return ps


def ensure_virtual_group(
    trader: Trader,
    currency: Currency,
    payment_system: PaymentSystem,
    traffic: TrafficType,
    *,
    label: str,
    in_active: bool,
) -> PaymentDetailsGroup:
    group = PaymentDetailsGroup.objects.filter(
        trader=trader,
        payment_system=payment_system,
        currency=currency,
    ).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner=f"{GROUP_OWNER} {label}",
            trader=trader,
            currency=currency,
            payment_system=payment_system,
            status=1,
            amount=Decimal("999999"),
            in_active=in_active,
            out_active=False,
            min_amount_out=Decimal("1000"),
            max_amount_out=Decimal("5000000"),
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
            current_volume=Decimal("0"),
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
        print(f"  + Virtual group {label} ({group.id}) in_active={in_active}")
        return group

    changed = False
    for field, val in (
        ("status", 1),
        ("in_active", in_active),
        ("amount", Decimal("999999")),
        ("current_volume", Decimal("0")),
    ):
        if getattr(group, field) != val:
            setattr(group, field, val)
            changed = True
    if changed:
        group.save()
    if not group.allowed_traffic.filter(pk=traffic.pk).exists():
        group.allowed_traffic.add(traffic)
    detail = PaymentDetails.objects.filter(group=group, status=1).first()
    if detail is None:
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
    print(f"  ~ virtual group {label} ({group.id}) in_active={group.in_active}")
    return group


def enforce_payplat_active_test_only(trader: Trader) -> None:
    """У payplat1 активна только C2CKZTTEST."""
    for group in PaymentDetailsGroup.objects.filter(trader=trader).select_related("payment_system"):
        ps_name = group.payment_system.name if group.payment_system else ""
        should_active = ps_name == ACTIVE_TEST_PS
        if group.in_active != should_active:
            group.in_active = should_active
            group.save(update_fields=["in_active"])
            print(f"  ~ payplat1 group {ps_name}: in_active={should_active}")


def run():
    print("=== PayPlat trader setup ===")
    lang = Language.objects.first() or Language.objects.create(name="Russian")
    kzt = ensure_currency("KZT", "Kazakhstani Tenge")
    currency_by_symbol = {"KZT": kzt}

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
            currency=kzt,
            is_boss=True,
            blocked=False,
        )
        print(f"  + Trader {TRADER_USERNAME}")
    elif trader.team_id != team.id:
        trader.team = team
        trader.save(update_fields=["team"])

    for ps_name, cur_sym, in_active in PS_ROWS:
        currency = currency_by_symbol[cur_sym]
        ps = ensure_payment_system(currency, ps_name)
        TraderTeamRates.objects.get_or_create(
            team=team,
            payment_system=ps,
            defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")},
        )
        ensure_virtual_group(
            trader,
            currency,
            ps,
            traffic,
            label=f"{cur_sym} {ps_name}",
            in_active=in_active,
        )

    enforce_payplat_active_test_only(trader)

    print("Done.")
    print("  Active for payplat1: only C2CKZTTEST")
    print("  1) shell_setup_payplat_c2ckzttest_routing.py — merchant + отключить другие PSP на C2CKZTTEST")
    print("  2) .env PAYPLAT_REQUISITE_TYPE_MAP с C2C/C2CKZT/C2CKZTTEST")
    print("  3) IPN URL → https://api.avapay.net/api/v1/webhooks/psp/payplat/")


run()
