"""
Живая киргизская команда / донастройка существующих трейдеров для Melbet local KGS.

PS уже есть (shell_setup_melbet_kgs_payplat.py), новые имена не нужны:
  QRKGS   = ELQR (телефон +996…)
  PHONEKGS = phone
  C2CKGS  = card

Существующие трейдеры (resdfe / resdfe1) — не трогает team/currency:
  CREATE_USERS=0 TRADER_USERNAMES=resdfe,resdfe1 \\
  docker compose exec -T -e CREATE_USERS -e TRADER_USERNAMES app \\
    python manage.py shell < titanpay/basics/shell_create_melbet_kgs_live_team.py

Новая команда:
  TEAM_NAME='KG Local' TRADER_USERNAMES=kg1,kg2 \\
  docker compose exec -T -e TEAM_NAME -e TRADER_USERNAMES app \\
    python manage.py shell < titanpay/basics/shell_create_melbet_kgs_live_team.py

Опционально: MDR_IN=7 MDR_OUT=2.5 PASSWORD=... USDT_BALANCE=5000 FORCE_TEAM=1
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from basics.models import (
    Balance,
    Currency,
    Language,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeam,
    TraderTeamRates,
    TrafficType,
)
from merchant.kzt_settlement import C2C_KGS_PS_NAME, KGS_PS_NAME, PHONE_KGS_PS_NAME

TEAM_NAME = os.environ.get("TEAM_NAME", "KG Local Melbet").strip() or "KG Local Melbet"
TRAFFIC_NAME = "Standard"
DEFAULT_PASSWORD = os.environ.get("PASSWORD", "KgTrader_ChangeMe_2026!").strip()
MDR_IN = Decimal(os.environ.get("MDR_IN", "7") or "7")
MDR_OUT = Decimal(os.environ.get("MDR_OUT", "2.5") or "2.5")
USDT_BALANCE = Decimal(os.environ.get("USDT_BALANCE", "5000") or "5000")
CREATE_USERS = os.environ.get("CREATE_USERS", "1").strip().lower() in ("1", "true", "yes")
# Не переносить существующих на TEAM_NAME / не менять currency (для resdfe).
FORCE_TEAM = os.environ.get("FORCE_TEAM", "0").strip().lower() in ("1", "true", "yes")
PS_NAMES = (KGS_PS_NAME, C2C_KGS_PS_NAME, PHONE_KGS_PS_NAME)


def _usernames() -> list[str]:
    raw = os.environ.get("TRADER_USERNAMES", "").strip()
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return ["kg_trader1"] if CREATE_USERS else []


def _ensure_rates(team: TraderTeam, payment_systems: list[PaymentSystem]) -> None:
    for ps in payment_systems:
        rate, created = TraderTeamRates.objects.get_or_create(
            team=team,
            payment_system=ps,
            defaults={"mdr_in": MDR_IN, "mdr_out": MDR_OUT},
        )
        if not created and (rate.mdr_in != MDR_IN or rate.mdr_out != MDR_OUT):
            rate.mdr_in = MDR_IN
            rate.mdr_out = MDR_OUT
            rate.save(update_fields=["mdr_in", "mdr_out"])
            print(f"  ~ rates team={team.name} {ps.name} mdr_in={rate.mdr_in}")
        else:
            print(f"  {'+' if created else '~'} rates team={team.name} {ps.name} mdr_in={rate.mdr_in}")


def run() -> None:
    print("=== Melbet KGS live team (human traders) ===")
    kgs = Currency.objects.filter(symbol="KGS").first()
    if kgs is None:
        print("ERROR: Currency KGS missing — run shell_setup_melbet_kgs_payplat.py first")
        return
    lang = Language.objects.order_by("id").first()
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    payment_systems: list[PaymentSystem] = []
    for name in PS_NAMES:
        ps = PaymentSystem.objects.filter(name=name, currency=kgs).first()
        if ps is None:
            print(f"ERROR: PaymentSystem {name} missing — run shell_setup_melbet_kgs_payplat.py")
            return
        if name == KGS_PS_NAME:
            want = {
                "qr_payload": {"regex": r".+", "pattern": "ELQR string / QR URL / data:image"},
                "phone": {"regex": r"^\+\d{10,15}$", "pattern": "Phone +996…"},
            }
            if ps.required_fields != want:
                ps.required_fields = want
                ps.save(update_fields=["required_fields"])
                print(f"  ~ PS {name} required_fields=qr_payload+phone")
            else:
                print(f"  ~ PS {name}")
        elif name == PHONE_KGS_PS_NAME:
            want = {"phone": {"regex": r"^\+\d{10,15}$", "pattern": "Phone +996…"}}
            if ps.required_fields != want:
                ps.required_fields = want
                ps.save(update_fields=["required_fields"])
                print(f"  ~ PS {name} required_fields=phone")
            else:
                print(f"  ~ PS {name}")
        else:
            print(f"  ~ PS {name}")
        payment_systems.append(ps)

    usernames = _usernames()
    fallback_team = TraderTeam.objects.filter(name=TEAM_NAME).first()
    if fallback_team is None and (CREATE_USERS or FORCE_TEAM or not usernames):
        fallback_team = TraderTeam.objects.create(name=TEAM_NAME)
        print(f"  + team {TEAM_NAME} id={fallback_team.id}")
    elif fallback_team is not None:
        print(f"  ~ team {TEAM_NAME} id={fallback_team.id}")

    if fallback_team is not None and (CREATE_USERS or FORCE_TEAM or not usernames):
        _ensure_rates(fallback_team, payment_systems)

    if not usernames:
        print("WARN: TRADER_USERNAMES пуст — ставки команды готовы, трейдеров не трогали")
        print("\nДальше в ЛК: QRKGS/PHONEKGS → +996… ; C2CKGS → карта 16 цифр")
        return

    touched_teams: set[int] = set()
    for i, uname in enumerate(usernames):
        user = User.objects.filter(username=uname).first()
        if user is None:
            if not CREATE_USERS:
                print(f"  ! user {uname} не найден (CREATE_USERS=0) — пропуск")
                continue
            user = User.objects.create_user(
                username=uname,
                email=f"{uname}@local.kg",
                password=DEFAULT_PASSWORD,
            )
            print(f"  + user {uname}")
        else:
            print(f"  ~ user {uname}")

        trader = Trader.objects.filter(user=user).select_related("team").first()
        if trader is None:
            if not CREATE_USERS:
                print(f"  ! trader {uname} не найден — пропуск")
                continue
            if fallback_team is None:
                print(f"  ! нет TEAM_NAME={TEAM_NAME} для нового трейдера")
                continue
            bal = Balance.objects.create(type=0, amount=USDT_BALANCE)
            frozen = Balance.objects.create(type=1, amount=Decimal("0"))
            trader = Trader.objects.create(
                user=user,
                team=fallback_team,
                currency=kgs,
                language=lang,
                balance_usdt=bal,
                frozen_balance_usdt=frozen,
                is_boss=(i == 0),
                manual_mode=True,
                telegram=f"@{uname}",
                phone="+996700000000",
            )
            print(f"  + trader {uname} boss={trader.is_boss} balance={USDT_BALANCE}")
        else:
            fields = []
            if FORCE_TEAM and fallback_team is not None and trader.team_id != fallback_team.id:
                trader.team = fallback_team
                fields.append("team")
            if FORCE_TEAM and trader.currency_id != kgs.id:
                trader.currency = kgs
                fields.append("currency")
            if not trader.manual_mode:
                trader.manual_mode = True
                fields.append("manual_mode")
            if fields:
                trader.save(update_fields=fields)
            team_label = trader.team.name if trader.team_id else None
            print(f"  ~ trader {uname} team={team_label} updated {fields or 'ok'}")

        if trader.team_id is None:
            print(f"  ! trader {uname} без команды — ставки некуда писать")
            continue
        if trader.team_id not in touched_teams:
            _ensure_rates(trader.team, payment_systems)
            touched_teams.add(trader.team_id)

        for ps in payment_systems:
            group = PaymentDetailsGroup.objects.filter(
                trader=trader, payment_system=ps, currency=kgs
            ).first()
            if group is None:
                group = PaymentDetailsGroup.objects.create(
                    owner=f"{uname} {ps.name}",
                    trader=trader,
                    currency=kgs,
                    payment_system=ps,
                    status=1,
                    amount=Decimal("999999"),
                    in_active=True,
                    out_active=False,
                    min_amount_out=Decimal("100"),
                    max_amount_out=Decimal("5000000"),
                    work_type="by_card",
                    deposit_number_on=False,
                    auto_live=timezone.now(),
                    current_volume=Decimal("0"),
                    limit_per_period=Decimal("999999999"),
                )
                group.allowed_traffic.add(traffic)
                print(f"    + group {ps.name} {group.id} (добавьте реквизит в ЛК)")
            else:
                group.status = 1
                group.in_active = True
                group.auto_live = timezone.now()
                group.save(update_fields=["status", "in_active", "auto_live", "updated_at"])
                group.allowed_traffic.add(traffic)
                print(f"    ~ group {ps.name} {group.id}")

    print("\nДальше в ЛК трейдера:")
    print("  QRKGS (ELQR)  → поле QR-код (строка ELQR / ссылка) + опционально +996…")
    print("  PHONEKGS      → телефон +996…")
    print("  C2CKGS        → карта 16 цифр")
    if CREATE_USERS:
        print(f"\nПароль новых юзеров (если создавались): {DEFAULT_PASSWORD}")
    print("Не добавляйте этих юзеров в PSP_TRADER_USERNAMES.")


run()
