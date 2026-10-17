"""
Локальный KGS (QR / LKQ) для Melbet через PayPlat.

Создаёт Currency KGS, PaymentSystem QRKGS, виртуальную группу payplat1,
MerchantSolution (melbet / melbet_test) и ключи method_map:
  default_kgs, qr_kgs, lkq, elqr → QRKGS + KGS

Не трогает публичную документацию и не перезаписывает KZT method_map.

Перед запуском в .env (если JSON задан явно — добавьте QRKGS):
  PAYPLAT_REQUISITE_TYPE_MAP=... ,"QRKGS":"lkq"}
  # payer для QRKGS не нужен; currency=kgs уходит в POST /deals

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_melbet_kgs_payplat.py

Опционально:
  MERCHANT_USERNAMES=melbet,melbet_test
  MIN_LIMIT_IN=100 MAX_LIMIT_IN=500000
  USDT_RATE=87
  OVERWRITE_LIMITS=0
  UPDATE_RATE=0
"""
from __future__ import annotations

import datetime
import os
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from basics.models import (
    Currency,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeamRates,
    TrafficType,
)
from basics.shell_merchant_solution import ensure_merchant_solution
from merchant.kzt_settlement import ensure_kgs_balances
from merchant.models import Merchant
from payments.integrations.melbet.models import MelbetIntegrationConfig
from payments.payplat_client import payplat_trader_username

PS_NAME = "QRKGS"
CURRENCY_SYMBOL = "KGS"
TRAFFIC_NAME = "Standard"
GROUP_OWNER = "PayPlat Virtual Drop"
DEFAULT_MDR_IN = Decimal("7")
DEFAULT_RATE = Decimal(os.environ.get("USDT_RATE", "87") or "87")
MIN_IN = Decimal(os.environ.get("MIN_LIMIT_IN", "100") or "100")
MAX_IN = Decimal(os.environ.get("MAX_LIMIT_IN", "500000") or "500000")
OVERWRITE_LIMITS = os.environ.get("OVERWRITE_LIMITS", "0").strip().lower() in ("1", "true", "yes")
UPDATE_RATE = os.environ.get("UPDATE_RATE", "0").strip().lower() in ("1", "true", "yes")

KGS_METHOD_MAP = {
    "default_kgs": {"payment_system": PS_NAME, "currency": "KGS"},
    "qr_kgs": {"payment_system": PS_NAME, "currency": "KGS"},
    "lkq": {"payment_system": PS_NAME, "currency": "KGS"},
    "elqr": {"payment_system": PS_NAME, "currency": "KGS"},
}


def _merchant_usernames() -> list[str]:
    raw = os.environ.get("MERCHANT_USERNAMES", "melbet,melbet_test").strip()
    return [u.strip() for u in raw.split(",") if u.strip()]


def ensure_currency() -> Currency:
    cur = Currency.objects.filter(symbol=CURRENCY_SYMBOL).first()
    if cur is None:
        cur = Currency.objects.create(symbol=CURRENCY_SYMBOL, name="Kyrgyz som")
        print(f"  + Currency {CURRENCY_SYMBOL}")
        return cur
    print(f"  ~ Currency {CURRENCY_SYMBOL}")
    return cur


def ensure_payment_system(currency: Currency) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=currency).first()
    if ps is None:
        ps = PaymentSystem.objects.create(
            name=PS_NAME,
            currency=currency,
            required_fields={},
            usdt_exchange_rate=DEFAULT_RATE,
            expired_time_in=datetime.timedelta(minutes=15),
            expired_time_out=datetime.timedelta(minutes=10),
            confirm_time_out=datetime.timedelta(minutes=10),
            constrain_time_out=datetime.timedelta(hours=4),
            in_on=True,
            out_on=False,
            sbp_compatible=False,
        )
        print(f"  + PaymentSystem {PS_NAME} rate={DEFAULT_RATE}")
        return ps
    fields: list[str] = []
    if not ps.in_on:
        ps.in_on = True
        fields.append("in_on")
    if UPDATE_RATE and ps.usdt_exchange_rate != DEFAULT_RATE:
        ps.usdt_exchange_rate = DEFAULT_RATE
        fields.append("usdt_exchange_rate")
    if fields:
        ps.save(update_fields=fields)
        print(f"  ~ PaymentSystem {PS_NAME} updated {fields}")
    else:
        print(f"  ~ PaymentSystem {PS_NAME} rate={ps.usdt_exchange_rate}")
    return ps


def ensure_payplat_group(trader: Trader, currency: Currency, ps: PaymentSystem, traffic: TrafficType) -> None:
    group = PaymentDetailsGroup.objects.filter(
        trader=trader, payment_system=ps, currency=currency
    ).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner=f"{GROUP_OWNER} {PS_NAME}",
            trader=trader,
            currency=currency,
            payment_system=ps,
            status=1,
            amount=Decimal("999999"),
            in_active=True,
            out_active=False,
            min_amount_out=Decimal("1000"),
            max_amount_out=Decimal("5000000"),
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
            current_volume=Decimal("0"),
        )
        group.allowed_traffic.add(traffic)
        print(f"  + group {PS_NAME} {group.id}")
    else:
        changed = False
        for field, val in (("status", 1), ("in_active", True), ("amount", Decimal("999999"))):
            if getattr(group, field) != val:
                setattr(group, field, val)
                changed = True
        if changed:
            group.save()
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ group {PS_NAME} {group.id} in_active={group.in_active}")

    if not PaymentDetails.objects.filter(group=group, status=1).exists():
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
        print(f"    + virtual card")


def merge_method_map(cfg: MelbetIntegrationConfig) -> None:
    current = dict(cfg.method_map) if isinstance(cfg.method_map, dict) else {}
    changed = False
    for key, entry in KGS_METHOD_MAP.items():
        if current.get(key) != entry:
            current[key] = entry
            changed = True
    if not changed:
        print(f"  ~ method_map already has KGS keys ({cfg.merchant.user.username})")
        return
    cfg.method_map = current
    cfg.save(update_fields=["method_map"])
    print(f"  + method_map KGS keys for {cfg.merchant.user.username}: {list(KGS_METHOD_MAP)}")


def run() -> None:
    print("=== Melbet KGS / QRKGS via PayPlat LKQ ===")
    username = payplat_trader_username()
    user = User.objects.filter(username=username).first()
    if user is None:
        print(f"ERROR: trader user {username!r} not found — run shell_create_payplat_trader.py")
        return
    trader = Trader.objects.filter(user=user).select_related("team").first()
    if trader is None:
        print(f"ERROR: trader {username!r} not found")
        return

    currency = ensure_currency()
    ps = ensure_payment_system(currency)
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    if trader.team_id:
        TraderTeamRates.objects.get_or_create(
            team=trader.team,
            payment_system=ps,
            defaults={"mdr_in": DEFAULT_MDR_IN, "mdr_out": Decimal("2.5")},
        )

    ensure_payplat_group(trader, currency, ps, traffic)

    limits = {
        "min_limit_in": MIN_IN,
        "max_limit_in": MAX_IN,
        "min_limit_out": MIN_IN,
        "max_limit_out": MAX_IN,
    }
    for uname in _merchant_usernames():
        mu = User.objects.filter(username=uname).first()
        merchant = Merchant.objects.filter(user=mu).first() if mu else None
        if merchant is None:
            print(f"  ! merchant {uname} not found — skip solutions/method_map")
            continue
        ensure_kgs_balances(merchant)
        print(f"  ~ {uname} balance_kgs={merchant.balance_kgs.amount if merchant.balance_kgs_id else 'n/a'}")
        ensure_merchant_solution(
            merchant,
            ps,
            traffic,
            overwrite_limits=OVERWRITE_LIMITS,
            limits=limits,
        )
        cfg = MelbetIntegrationConfig.objects.filter(merchant=merchant).first()
        if cfg is None:
            print(f"  ! no MelbetIntegrationConfig for {uname}")
            continue
        if not cfg.active:
            print(f"  ! MelbetIntegrationConfig for {uname} is inactive")
        merge_method_map(cfg)

    print("\n.env reminder (merge into existing JSON, do not drop C2CKZT):")
    print('  PAYPLAT_REQUISITE_TYPE_MAP=... "QRKGS":"lkq"')
    print("  # do not set payer=kz for QRKGS; deals send currency=kgs")
    print("\nMelbet method to send: qr_kgs  currency: kgs")


run()
