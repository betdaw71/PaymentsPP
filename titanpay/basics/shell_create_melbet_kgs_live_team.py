"""
Живая киргизская команда для Melbet local KGS (карта / телефон / ELQR).

Не PSP: реквизиты вводят вручную в ЛК. PS уже должны существовать
(shell_setup_melbet_kgs_payplat.py) — новые имена PS не нужны:
  QRKGS   = local KGS ELQR (телефон +996…)
  PHONEKGS = local KGS phone
  C2CKGS  = local KGS card

Создаёт / обновляет:
  - TraderTeam + TraderTeamRates на QRKGS / C2CKGS / PHONEKGS
  - трейдеров (currency=KGS, manual_mode=True) или цепляет существующих
  - пустые активные группы на каждый PS (реки добавят в ЛК)

Новая команда:
  TEAM_NAME='KG Local' TRADER_USERNAMES=kg_trader1,kg_trader2 \\
  docker compose exec -T -e TEAM_NAME -e TRADER_USERNAMES app \\
    python manage.py shell < titanpay/basics/shell_create_melbet_kgs_live_team.py

Существующая команда (только ставки + группы на юзеров):
  TEAM_NAME='ИмяКоманды' TRADER_USERNAMES=user1,user2 CREATE_USERS=0 \\
  docker compose exec -T -e TEAM_NAME -e TRADER_USERNAMES -e CREATE_USERS app \\
    python manage.py shell < titanpay/basics/shell_create_melbet_kgs_live_team.py

Опционально:
  PASSWORD=... MDR_IN=7 USDT_BALANCE=5000
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
PS_NAMES = (KGS_PS_NAME, C2C_KGS_PS_NAME, PHONE_KGS_PS_NAME)


def _usernames() -> list[str]:
    raw = os.environ.get("TRADER_USERNAMES", "").strip()
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return ["kg_trader1"] if CREATE_USERS else []


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
        # Живые ELQR/phone: в ЛК нужен required_fields.phone
        if name in (KGS_PS_NAME, PHONE_KGS_PS_NAME):
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

    team = TraderTeam.objects.filter(name=TEAM_NAME).first()
    if team is None:
        team = TraderTeam.objects.create(name=TEAM_NAME)
        print(f"  + team {TEAM_NAME} id={team.id}")
    else:
        print(f"  ~ team {TEAM_NAME} id={team.id}")

    for ps in payment_systems:
        rate, created = TraderTeamRates.objects.get_or_create(
            team=team,
            payment_system=ps,
            defaults={"mdr_in": MDR_IN, "mdr_out": MDR_OUT},
        )
        if not created and rate.mdr_in != MDR_IN:
            rate.mdr_in = MDR_IN
            rate.mdr_out = MDR_OUT
            rate.save(update_fields=["mdr_in", "mdr_out"])
            print(f"  ~ rates {ps.name} mdr_in={rate.mdr_in}")
        else:
            print(f"  {'+' if created else '~'} rates {ps.name} mdr_in={rate.mdr_in}")

    usernames = _usernames()
    if not usernames:
        print("WARN: TRADER_USERNAMES пуст — ставки команды готовы, трейдеров не трогали")
        print("\nДальше в ЛК трейдера:")
        print("  QRKGS (ELQR)  → телефон +996…")
        print("  PHONEKGS      → телефон +996…")
        print("  C2CKGS        → карта 16 цифр")
        return

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

        trader = Trader.objects.filter(user=user).first()
        if trader is None:
            if not CREATE_USERS:
                print(f"  ! trader {uname} не найден — пропуск")
                continue
            bal = Balance.objects.create(type=0, amount=USDT_BALANCE)
            frozen = Balance.objects.create(type=1, amount=Decimal("0"))
            trader = Trader.objects.create(
                user=user,
                team=team,
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
            if trader.team_id != team.id:
                trader.team = team
                fields.append("team")
            if trader.currency_id != kgs.id:
                trader.currency = kgs
                fields.append("currency")
            if not trader.manual_mode:
                trader.manual_mode = True
                fields.append("manual_mode")
            if fields:
                trader.save(update_fields=fields)
            print(f"  ~ trader {uname} updated {fields or 'ok'}")

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
    print("  QRKGS (ELQR)  → телефон +996…")
    print("  PHONEKGS      → телефон +996…")
    print("  C2CKGS        → карта 16 цифр")
    if CREATE_USERS:
        print(f"\nПароль новых юзеров (если создавались): {DEFAULT_PASSWORD}")
    print("Не добавляйте этих юзеров в PSP_TRADER_USERNAMES.")


run()
