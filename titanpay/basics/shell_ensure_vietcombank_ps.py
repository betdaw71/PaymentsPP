"""Создать банк-PaymentSystem в KZT (по умолчанию Vietcombank) и ставки команд с C2CKZT.

Мерчант по-прежнему шлёт C2C / C2CKZT. Роутинг берёт группы банка,
в реквизитах bank=имя PS. Наценка курса — XE_KZT_MARKUP_BY_PS, иначе XE_KZT_MARKUP.
Имя банка обязано быть в KZT_C2C_BANK_PS_NAMES, иначе роутинг его не подхватит.

Запуск (BANK_PS_NAME задаёт банк):
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_ensure_vietcombank_ps.py

Опционально создать группу реквизитов трейдеру:
  TRADER_USERNAME=ivan docker compose exec -T app env TRADER_USERNAME=ivan \\
    python manage.py shell < titanpay/basics/shell_ensure_vietcombank_ps.py

Переменные группы (пустое значение = дефолт):
  IN_ACTIVE / OUT_ACTIVE     — направления группы, по умолчанию оба включены
  GROUP_AMOUNT / CARD_AMOUNT — баланс группы и карты, по умолчанию 999999
  MIN_AMOUNT_IN / MAX_AMOUNT_IN, LIMIT_PER_PERIOD — лимиты pay-in
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
from basics.utils import xe_kzt_markup_for_ps
from titanpay.settings import C2C_NAME, C2CKZT_NAME, KZT_C2C_BANK_PS_NAMES
from trade.routing.ps_names import kzt_c2c_bank_ps_names

BANK_PS_NAME = (os.environ.get("BANK_PS_NAME") or "Vietcombank").strip()
TRADER_USERNAME = (os.environ.get("TRADER_USERNAME") or "").strip()
CARD_NUMBER = (os.environ.get("CARD_NUMBER") or "").strip()
OWNER = (os.environ.get("OWNER") or "").strip()


def _flag(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _decimal(name: str, default):
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return Decimal(raw)


IN_ACTIVE = _flag("IN_ACTIVE", True)
OUT_ACTIVE = _flag("OUT_ACTIVE", True)
GROUP_AMOUNT = _decimal("GROUP_AMOUNT", Decimal("999999"))
CARD_AMOUNT = _decimal("CARD_AMOUNT", GROUP_AMOUNT)
MIN_AMOUNT_IN = _decimal("MIN_AMOUNT_IN", None)
MAX_AMOUNT_IN = _decimal("MAX_AMOUNT_IN", None)
LIMIT_PER_PERIOD = _decimal("LIMIT_PER_PERIOD", None)


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


def _ensure_team_rates_for_trader(trader: Trader, bank_ps: PaymentSystem):
    """Без ставок команды на банке get_teams_for_payment_systems не вернёт её в pay-in роутинг."""
    team = trader.team
    if team is None:
        print(f"  ! trader {trader.user.username} has no team — routing will skip the group")
        return
    if TraderTeamRates.objects.filter(team=team, payment_system=bank_ps).exists():
        print(f"  ~ TraderTeamRates team={team.name} ps={bank_ps.name}")
        return
    source = (
        TraderTeamRates.objects.filter(team=team, payment_system__name=C2CKZT_NAME).first()
        or TraderTeamRates.objects.filter(team=team).first()
    )
    if source is None:
        print(f"  ! team {team.name} has no rates to copy — set mdr for {bank_ps.name} manually")
        return
    TraderTeamRates.objects.create(
        team=team,
        payment_system=bank_ps,
        mdr_in=source.mdr_in,
        mdr_out=source.mdr_out,
    )
    src_name = source.payment_system.name if source.payment_system_id else "?"
    print(f"  + TraderTeamRates team={team.name} ps={bank_ps.name} "
          f"mdr_in={source.mdr_in} mdr_out={source.mdr_out} (from {src_name})")


def _maybe_trader_group(bank_ps: PaymentSystem, kzt: Currency):
    if not TRADER_USERNAME:
        return
    trader = Trader.objects.filter(user__username=TRADER_USERNAME).select_related("user", "team").first()
    if trader is None:
        print(f"  ! trader {TRADER_USERNAME!r} not found — skip group")
        return
    _ensure_team_rates_for_trader(trader, bank_ps)
    traffic = TrafficType.objects.filter(name="Standard").first() or TrafficType.objects.first()
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=bank_ps).first()
    if group is None:
        kwargs = {
            "trader": trader,
            "currency": kzt,
            "payment_system": bank_ps,
            "status": 1,
            "owner": OWNER,
            "amount": GROUP_AMOUNT,
            "in_active": IN_ACTIVE,
            "out_active": OUT_ACTIVE,
            "min_amount_out": Decimal("1000"),
            "max_amount_out": Decimal("5000000"),
            "work_type": "by_card",
            "deposit_number_on": False,
            "auto_live": timezone.now(),
        }
        if MIN_AMOUNT_IN is not None:
            kwargs["min_amount_in"] = MIN_AMOUNT_IN
        if MAX_AMOUNT_IN is not None:
            kwargs["max_amount_in"] = MAX_AMOUNT_IN
        if LIMIT_PER_PERIOD is not None:
            kwargs["limit_per_period"] = LIMIT_PER_PERIOD
        group = PaymentDetailsGroup.objects.create(**kwargs)
        if traffic:
            group.allowed_traffic.add(traffic)
        print(f"  + group {group.id} trader={TRADER_USERNAME} ps={bank_ps.name}")
    else:
        print(f"  ~ group {group.id} trader={TRADER_USERNAME} ps={bank_ps.name} — оставляю как есть")
    print(f"    status={group.status} in_active={group.in_active} out_active={group.out_active} "
          f"amount={group.amount}")
    print(f"    in=[{group.min_amount_in} .. {group.max_amount_in}] "
          f"limit_per_period={group.limit_per_period} "
          f"out=[{group.min_amount_out} .. {group.max_amount_out}]")
    print(f"    traffic={[t.name for t in group.allowed_traffic.all()]}")
    if CARD_NUMBER:
        digits = "".join(c for c in CARD_NUMBER if c.isdigit())
        if PaymentDetails.objects.filter(group=group, card_number=digits, status=1).exists():
            print(f"  ~ card already on group")
            return
        PaymentDetails.objects.create(
            group=group,
            status=1,
            amount=CARD_AMOUNT,
            card_number=digits,
            deposit_number=str(abs(hash(digits)))[:20].zfill(20),
            sberpay_enabled=False,
            sbp_enabled=False,
        )
        print(f"  + card {digits[-4:]} on group {group.id} amount={CARD_AMOUNT}")


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
    print(f"Trader group must be on {BANK_PS_NAME} (KZT).")
    if BANK_PS_NAME not in kzt_c2c_bank_ps_names():
        print(f"! {BANK_PS_NAME} is NOT in KZT_C2C_BANK_PS_NAMES — routing will ignore it.")
        print(f"  Add it to .env and restart: "
              f"KZT_C2C_BANK_PS_NAMES={','.join(sorted(kzt_c2c_bank_ps_names() | {BANK_PS_NAME}))}")
    print(f"Rate markup: xe_kzt_markup_for_ps({BANK_PS_NAME}) = {xe_kzt_markup_for_ps(BANK_PS_NAME)}")
    print("Check: python manage.py diagnose_routing <merchant> --ps C2CKZT --amount 10000 --ftd false")


run()
