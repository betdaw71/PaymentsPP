"""Kyrgyz bank PaymentSystems for KZT transborder (C2CKZT).

Merchant still sends C2C/C2CKZT. Trader creates cards on these PS names;
routing includes the groups and payment_details.bank = PS name.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_ensure_kg_kzt_transborder_banks.py

  docker compose exec -T -e TRADER_USERNAME=resdfe app python manage.py shell \\
    < titanpay/basics/shell_ensure_kg_kzt_transborder_banks.py

.env (must include Vietcombank + these names, then restart app):
  KZT_C2C_BANK_PS_NAMES=Vietcombank,Elkard,Kompanion,Mbank,Optima,O bank,Bai-Tushum
"""
from __future__ import annotations

import datetime
import os
from decimal import Decimal

from django.utils import timezone

from basics.models import (
    Currency,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeamRates,
    TrafficType,
)
from titanpay.settings import C2C_NAME, C2CKZT_NAME
from trade.routing.ps_names import kzt_c2c_bank_ps_names

BANK_PS_NAMES = (
    "Elkard",
    "Kompanion",
    "Mbank",
    "Optima",
    "O bank",
    "Bai-Tushum",
)
TRADER_USERNAME = (os.environ.get("TRADER_USERNAME") or "resdfe").strip()
TRADER_MDR_IN = Decimal((os.environ.get("TRADER_MDR_IN") or "4.5").strip())


def _ensure_ps(kzt: Currency, name: str, template: PaymentSystem | None) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=name, currency=kzt).first()
    if ps:
        fields: list[str] = []
        if not ps.in_on:
            ps.in_on = True
            fields.append("in_on")
        if template and not ps.required_fields:
            ps.required_fields = template.required_fields
            fields.append("required_fields")
        if fields:
            ps.save(update_fields=fields)
            print(f"  ~ PaymentSystem {name!r} id={ps.id} updated {fields}")
        else:
            print(f"  ~ PaymentSystem {name!r} id={ps.id}")
        return ps
    kwargs = {
        "name": name,
        "currency": kzt,
        "required_fields": (
            template.required_fields
            if template and isinstance(template.required_fields, dict) and template.required_fields
            else {"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}}
        ),
        "usdt_exchange_rate": (template.usdt_exchange_rate if template else Decimal("520")),
        "expired_time_in": template.expired_time_in if template else datetime.timedelta(minutes=15),
        "expired_time_out": template.expired_time_out if template else datetime.timedelta(minutes=10),
        "confirm_time_out": template.confirm_time_out if template else datetime.timedelta(minutes=10),
        "constrain_time_out": template.constrain_time_out if template else datetime.timedelta(hours=4),
        "in_on": True,
        "out_on": False,
        "sbp_compatible": False,
    }
    ps = PaymentSystem.objects.create(**kwargs)
    print(f"  + PaymentSystem {name!r} id={ps.id}")
    return ps


def _sync_team_rates(src: PaymentSystem, dst: PaymentSystem) -> None:
    for row in TraderTeamRates.objects.filter(payment_system=src).select_related("team"):
        if TraderTeamRates.objects.filter(team=row.team, payment_system=dst).exists():
            continue
        TraderTeamRates.objects.create(
            team=row.team,
            payment_system=dst,
            mdr_in=row.mdr_in,
            mdr_out=row.mdr_out,
        )
        print(f"  + TraderTeamRates team={row.team.name} ps={dst.name!r} mdr_in={row.mdr_in}")


def _ensure_team_rates_for_trader(trader: Trader, bank_ps: PaymentSystem) -> None:
    team = trader.team
    if team is None:
        print(f"  ! trader {trader.user.username} has no team — routing will skip groups")
        return
    source = TraderTeamRates.objects.filter(team=team, payment_system__name=C2CKZT_NAME).first()
    mdr_out = source.mdr_out if source else Decimal("2.5")
    existing = TraderTeamRates.objects.filter(team=team, payment_system=bank_ps).first()
    if existing:
        if existing.mdr_in == TRADER_MDR_IN:
            print(f"  ~ TraderTeamRates team={team.name} ps={bank_ps.name!r} mdr_in={existing.mdr_in}")
            return
        existing.mdr_in = TRADER_MDR_IN
        existing.save(update_fields=["mdr_in"])
        print(f"  ~ TraderTeamRates team={team.name} ps={bank_ps.name!r} mdr_in={TRADER_MDR_IN}")
        return
    TraderTeamRates.objects.create(
        team=team,
        payment_system=bank_ps,
        mdr_in=TRADER_MDR_IN,
        mdr_out=mdr_out,
    )
    print(f"  + TraderTeamRates team={team.name} ps={bank_ps.name!r} mdr_in={TRADER_MDR_IN}")


def _ensure_trader_group(trader: Trader, bank_ps: PaymentSystem, kzt: Currency) -> None:
    _ensure_team_rates_for_trader(trader, bank_ps)
    traffic = TrafficType.objects.filter(name="Standard").first() or TrafficType.objects.first()
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=bank_ps).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            trader=trader,
            currency=kzt,
            payment_system=bank_ps,
            status=1,
            owner="",
            amount=Decimal("999999"),
            in_active=True,
            out_active=False,
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
            limit_per_period=Decimal("50000000"),
        )
        if traffic:
            group.allowed_traffic.add(traffic)
        print(f"  + group {group.id} trader={trader.user.username} ps={bank_ps.name!r}")
        return
    changed = False
    if group.status != 1:
        group.status = 1
        changed = True
    if not group.in_active:
        group.in_active = True
        changed = True
    if changed:
        group.updated_at = timezone.now()
        group.save(update_fields=["status", "in_active", "updated_at"])
    if traffic and not group.allowed_traffic.filter(pk=traffic.pk).exists():
        group.allowed_traffic.add(traffic)
    print(f"  ~ group {group.id} trader={trader.user.username} ps={bank_ps.name!r} in_active={group.in_active}")


def run() -> None:
    print("=== KG banks → C2CKZT transborder ===")
    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        print("  ! Currency KZT not found")
        return
    template = (
        PaymentSystem.objects.filter(name=C2CKZT_NAME, currency=kzt).first()
        or PaymentSystem.objects.filter(name=C2C_NAME, currency=kzt).first()
    )
    c2ckzt = PaymentSystem.objects.filter(name=C2CKZT_NAME, currency=kzt).first()
    c2c_kzt = PaymentSystem.objects.filter(name=C2C_NAME, currency=kzt).first()
    trader = (
        Trader.objects.filter(user__username=TRADER_USERNAME).select_related("user", "team").first()
        if TRADER_USERNAME
        else None
    )
    if TRADER_USERNAME and trader is None:
        print(f"  ! trader {TRADER_USERNAME!r} not found — creating PS only")

    routed = kzt_c2c_bank_ps_names()
    missing_env = [name for name in BANK_PS_NAMES if name not in routed]
    systems = []
    for name in BANK_PS_NAMES:
        bank_ps = _ensure_ps(kzt, name, template)
        systems.append(bank_ps)
        for src in (c2ckzt, c2c_kzt, template):
            if src is None:
                continue
            _sync_team_rates(src, bank_ps)
            _sync_team_rates(bank_ps, src)
        if trader is not None:
            _ensure_trader_group(trader, bank_ps, kzt)

    print("")
    print("Trader LK: pick payment system Elkard / Kompanion / Mbank / Optima / O bank / Bai-Tushum.")
    print("Merchant still sends payment_system=C2CKZT (or C2C). bank in requisites = PS name.")
    if missing_env:
        print(f"! Not in KZT_C2C_BANK_PS_NAMES: {missing_env}")
        print(
            "  Add to .env and restart app:"
        )
        print(
            "  KZT_C2C_BANK_PS_NAMES="
            + ",".join(["Vietcombank", *BANK_PS_NAMES])
        )
    else:
        print("  KZT_C2C_BANK_PS_NAMES already includes these banks.")
    print("  python manage.py diagnose_routing <merchant> --ps C2CKZT --amount 10000 --ftd false")


run()
