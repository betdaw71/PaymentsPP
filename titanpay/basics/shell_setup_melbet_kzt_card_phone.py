"""
Melbet KZT: два method — карта (C2CKZT / PayPlat CARD) и телефон (PHONEKZT / MOBILE).

Не меняет C2CKZT/h2h у других мерчантов. KZT-ledger Melbet включает PHONEKZT.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_melbet_kzt_card_phone.py

Опционально: MERCHANT_USERNAMES=melbet,melbet_test
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
from merchant.kzt_settlement import PHONE_KZT_PS_NAME
from merchant.models import Merchant, MerchantSolution
from payments.integrations.melbet.models import MelbetIntegrationConfig
from payments.payplat_client import payplat_trader_username

TRAFFIC_NAME = "Standard"
GROUP_OWNER = "PayPlat Virtual Drop"
CARD_PS = "C2CKZT"
PHONE_PS = PHONE_KZT_PS_NAME
DEFAULT_MDR_IN = Decimal("7")

PHONE_METHOD_MAP = {
    "phone_kzt": {"payment_system": PHONE_PS, "currency": "KZT"},
    "mobile_kzt": {"payment_system": PHONE_PS, "currency": "KZT"},
}


def _merchant_usernames() -> list[str]:
    raw = os.environ.get("MERCHANT_USERNAMES", "melbet,melbet_test").strip()
    return [u.strip() for u in raw.split(",") if u.strip()]


def ensure_phone_ps(kzt: Currency, card_ps: PaymentSystem | None) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=PHONE_PS, currency=kzt).first()
    rate = card_ps.usdt_exchange_rate if card_ps is not None else Decimal("500")
    if ps is None:
        ps = PaymentSystem.objects.create(
            name=PHONE_PS,
            currency=kzt,
            required_fields={
                "phone": {"regex": r"^\+?\d{10,15}$", "pattern": "Phone number"},
            },
            usdt_exchange_rate=rate,
            expired_time_in=datetime.timedelta(minutes=15),
            expired_time_out=datetime.timedelta(minutes=10),
            confirm_time_out=datetime.timedelta(minutes=10),
            constrain_time_out=datetime.timedelta(hours=4),
            in_on=True,
            out_on=False,
            sbp_compatible=False,
        )
        print(f"  + PaymentSystem {PHONE_PS} rate={rate}")
        return ps
    fields: list[str] = []
    if not ps.in_on:
        ps.in_on = True
        fields.append("in_on")
    if card_ps is not None and ps.usdt_exchange_rate != card_ps.usdt_exchange_rate:
        ps.usdt_exchange_rate = card_ps.usdt_exchange_rate
        fields.append("usdt_exchange_rate")
    if fields:
        ps.save(update_fields=fields)
        print(f"  ~ PaymentSystem {PHONE_PS} updated {fields}")
    else:
        print(f"  ~ PaymentSystem {PHONE_PS} rate={ps.usdt_exchange_rate}")
    return ps


def ensure_payplat_group(trader: Trader, kzt: Currency, ps: PaymentSystem, traffic: TrafficType) -> None:
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=ps, currency=kzt).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner=f"{GROUP_OWNER} {ps.name}",
            trader=trader,
            currency=kzt,
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
        print(f"  + group {ps.name} {group.id}")
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
        print(f"  ~ group {ps.name} {group.id} in_active={group.in_active}")
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
        print("    + virtual card")


def limits_from_card_solution(merchant: Merchant, card_ps: PaymentSystem | None) -> dict:
    if card_ps is None:
        return {
            "min_limit_in": Decimal("1000"),
            "max_limit_in": Decimal("1000000"),
            "min_limit_out": Decimal("1000"),
            "max_limit_out": Decimal("1000000"),
        }
    src = MerchantSolution.objects.filter(merchant=merchant, payment_system=card_ps, ftd=False).first()
    if src is None:
        src = MerchantSolution.objects.filter(merchant=merchant, payment_system=card_ps).first()
    if src is None:
        return {
            "min_limit_in": Decimal("1000"),
            "max_limit_in": Decimal("1000000"),
            "min_limit_out": Decimal("1000"),
            "max_limit_out": Decimal("1000000"),
        }
    return {
        "min_limit_in": src.min_limit_in,
        "max_limit_in": src.max_limit_in,
        "min_limit_out": src.min_limit_out,
        "max_limit_out": src.max_limit_out,
    }


def merge_method_map(cfg: MelbetIntegrationConfig) -> None:
    current = dict(cfg.method_map) if isinstance(cfg.method_map, dict) else {}
    changed = False
    for key, entry in PHONE_METHOD_MAP.items():
        if current.get(key) != entry:
            current[key] = entry
            changed = True
    if not changed:
        print(f"  ~ method_map already has phone keys ({cfg.merchant.user.username})")
        return
    cfg.method_map = current
    cfg.save(update_fields=["method_map"])
    print(f"  + method_map phone keys for {cfg.merchant.user.username}: {list(PHONE_METHOD_MAP)}")


def run() -> None:
    print("=== Melbet KZT card / phone split ===")
    username = payplat_trader_username()
    user = User.objects.filter(username=username).first()
    if user is None:
        print(f"ERROR: trader user {username!r} not found")
        return
    trader = Trader.objects.filter(user=user).select_related("team").first()
    if trader is None:
        print(f"ERROR: trader {username!r} not found")
        return

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        print("ERROR: Currency KZT not found")
        return
    card_ps = PaymentSystem.objects.filter(name=CARD_PS, currency=kzt).first()
    phone_ps = ensure_phone_ps(kzt, card_ps)
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    if trader.team_id:
        TraderTeamRates.objects.get_or_create(
            team=trader.team,
            payment_system=phone_ps,
            defaults={"mdr_in": DEFAULT_MDR_IN, "mdr_out": Decimal("2.5")},
        )
    ensure_payplat_group(trader, kzt, phone_ps, traffic)

    for uname in _merchant_usernames():
        mu = User.objects.filter(username=uname).first()
        merchant = Merchant.objects.filter(user=mu).first() if mu else None
        if merchant is None:
            print(f"  ! merchant {uname} not found")
            continue
        ensure_merchant_solution(
            merchant,
            phone_ps,
            traffic,
            overwrite_limits=False,
            limits=limits_from_card_solution(merchant, card_ps),
        )
        cfg = MelbetIntegrationConfig.objects.filter(merchant=merchant).first()
        if cfg is None:
            print(f"  ! no MelbetIntegrationConfig for {uname}")
            continue
        merge_method_map(cfg)

    print("\nMelbet methods:")
    print("  card2card_kzt / card2card_kzt_kaspi / card2card_kzt_halyk  → C2CKZT  (PayPlat CARD)")
    print("  phone_kzt / mobile_kzt  → PHONEKZT  (PayPlat MOBILE)")
    print("\n.env reminder: PAYPLAT_REQUISITE_TYPE_MAP ... \"PHONEKZT\":\"mobile\"")
    print("  C2CKZT for other merchants stays h2h; Melbet C2CKZT is forced to card in code.")


run()
