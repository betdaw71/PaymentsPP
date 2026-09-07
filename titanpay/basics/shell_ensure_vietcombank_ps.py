"""Создать PaymentSystem Vietcombank (KZT) и ставки команд с C2CKZT.

Мерчант по-прежнему шлёт C2C / C2CKZT. Роутинг берёт группы Vietcombank,
в реквизитах bank=Vietcombank. Курс: XE KZT +4% (XE_KZT_MARKUP_BY_PS).

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_ensure_vietcombank_ps.py

Опционально создать группу реквизитов трейдеру:
  TRADER_USERNAME=ivan docker compose exec -T app env TRADER_USERNAME=ivan \\
    python manage.py shell < titanpay/basics/shell_ensure_vietcombank_ps.py
"""
from __future__ import annotations

import datetime
import os
from decimal import Decimal

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
from titanpay.settings import C2C_NAME, C2CKZT_NAME, KZT_C2C_BANK_PS_NAMES

BANK_PS_NAME = (os.environ.get("BANK_PS_NAME") or "Vietcombank").strip()
TRADER_USERNAME = (os.environ.get("TRADER_USERNAME") or "").strip()
CARD_NUMBER = (os.environ.get("CARD_NUMBER") or "").strip()
OWNER = (os.environ.get("OWNER") or "").strip()


def _parse_bank_names() -> list[str]:
    raw = KZT_C2C_BANK_PS_NAMES or BANK_PS_NAME
    names = [p.strip() for p in str(raw).split(",") if p.strip()]
    if BANK_PS_NAME not in names:
        names.append(BANK_PS_NAME)
    return names


def _copy_required_fields(source: PaymentSystem | None) -> dict:
    if source and isinstance(source.required_fields, dict) and source.required_fields:
        return source.required_fields
    return {"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}}


def _ensure_ps(kzt: Currency, name: str, template: PaymentSystem | None) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=name, currency=kzt).first()
    if ps:
        print(f"  ~ PaymentSystem {name} id={ps.id}")
        return ps
    kwargs = {
        "name": name,
        "currency": kzt,
        "required_fields": _copy_required_fields(template),
        "usdt_exchange_rate": (template.usdt_exchange_rate if template else Decimal("520")),
        "expired_time_in": template.expired_time_in if template else datetime.timedelta(minutes=15),
        "expired_time_out": template.expired_time_out if template else datetime.timedelta(minutes=10),
        "confirm_time_out": template.confirm_time_out if template else datetime.timedelta(minutes=10),
        "constrain_time_out": template.constrain_time_out if template else datetime.timedelta(hours=4),
        "in_on": True,
        "out_on": True,
    }
    ps = PaymentSystem.objects.create(**kwargs)
    print(f"  + PaymentSystem {name} id={ps.id}")
    return ps


def _sync_team_rates(src: PaymentSystem, dst: PaymentSystem):
    for row in TraderTeamRates.objects.filter(payment_system=src).select_related("team"):
        existing = TraderTeamRates.objects.filter(team=row.team, payment_system=dst).first()
        if existing:
            continue
        TraderTeamRates.objects.create(
            team=row.team,
            payment_system=dst,
            mdr_in=row.mdr_in,
            mdr_out=row.mdr_out,
        )
        print(f"  + TraderTeamRates team={row.team.name} ps={dst.name} mdr_in={row.mdr_in}")


def _maybe_trader_group(bank_ps: PaymentSystem, kzt: Currency):
    if not TRADER_USERNAME:
        return
    trader = Trader.objects.filter(user__username=TRADER_USERNAME).select_related("user", "team").first()
    if trader is None:
        print(f"  ! trader {TRADER_USERNAME!r} not found — skip group")
        return
    traffic = TrafficType.objects.filter(name="Standard").first() or TrafficType.objects.first()
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=bank_ps).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            trader=trader,
            currency=kzt,
            payment_system=bank_ps,
            status=1,
            owner=OWNER,
            amount=Decimal("999999"),
            in_active=True,
            out_active=True,
            min_amount_out=Decimal("1000"),
            max_amount_out=Decimal("5000000"),
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
        )
        if traffic:
            group.allowed_traffic.add(traffic)
        print(f"  + group {group.id} trader={TRADER_USERNAME} ps={bank_ps.name}")
    else:
        print(f"  ~ group {group.id} trader={TRADER_USERNAME} ps={bank_ps.name}")
    if CARD_NUMBER:
        digits = "".join(c for c in CARD_NUMBER if c.isdigit())
        if PaymentDetails.objects.filter(group=group, card_number=digits, status=1).exists():
            print(f"  ~ card already on group")
            return
        PaymentDetails.objects.create(
            group=group,
            status=1,
            amount=Decimal("999999"),
            card_number=digits,
            deposit_number=str(abs(hash(digits)))[:20].zfill(20),
            sberpay_enabled=False,
            sbp_enabled=False,
        )
        print(f"  + card {digits[-4:]} on group {group.id}")


def run():
    print(f"=== Ensure KZT bank PS ({BANK_PS_NAME}) ===")
    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        kzt = Currency.objects.create(symbol="KZT", name="Kazakhstani Tenge")
        print("  + Currency KZT")
    template = (
        PaymentSystem.objects.filter(name=C2CKZT_NAME, currency=kzt).first()
        or PaymentSystem.objects.filter(name=C2C_NAME, currency=kzt).first()
    )
    c2c_kzt = PaymentSystem.objects.filter(name=C2C_NAME, currency=kzt).first()
    c2ckzt = PaymentSystem.objects.filter(name=C2CKZT_NAME, currency=kzt).first()
    if template is None:
        print("  ! C2CKZT/C2C KZT not found — creating bank PS with defaults")
    for name in _parse_bank_names():
        bank_ps = _ensure_ps(kzt, name, template)
        for src in (c2ckzt, c2c_kzt, template):
            if src is None:
                continue
            _sync_team_rates(src, bank_ps)
            _sync_team_rates(bank_ps, src)
        if name == BANK_PS_NAME:
            _maybe_trader_group(bank_ps, kzt)
    print("")
    print("Merchant keeps requesting payment_system=C2C or C2CKZT.")
    print("Trader group must be on Vietcombank (KZT).")
    print("Rate: XE_KZT_MARKUP_BY_PS Vietcombank=1.04")
    print("Check: python manage.py diagnose_routing <merchant> --ps C2CKZT --amount 10000 --ftd false")


run()
