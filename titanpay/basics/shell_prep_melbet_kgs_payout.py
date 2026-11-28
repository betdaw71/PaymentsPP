"""
Подготовка Melbet local KGS payout: out_on на PS + тестовый трейдер out_active.

После этого Melbet может слать POST /withdrawal/ (currency=KGS, method=card2card_kgs|phone_kgs)
и мы принимаем заявку (In Progress), а не 400 Cannot process.

  docker compose exec -T app python manage.py shell < titanpay/basics/shell_prep_melbet_kgs_payout.py

Опционально:
  TRADER=melbet_kgs_payout_test
  TOPUP_KGS=100000   # пополнить melbet.balance_kgs (ledger может и уходить в минус)
  PREFERRED=1        # печать PAYOUT_PREFERRED_TRADER_BY_MERCHANT для .env
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

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
from merchant.kzt_settlement import (
    C2C_KGS_PS_NAME,
    KGS_PS_NAME,
    PHONE_KGS_PS_NAME,
    ensure_kgs_balances,
)
from merchant.models import Merchant

TRADER = (os.environ.get("TRADER") or "melbet_kgs_payout_test").strip() or "melbet_kgs_payout_test"
TEAM_NAME = (os.environ.get("TEAM_NAME") or "Melbet KGS Payout Test").strip()
MDR_OUT = Decimal(os.environ.get("MDR_OUT", "2.5") or "2.5")
MDR_IN = Decimal(os.environ.get("MDR_IN", "7") or "7")
PASSWORD = (os.environ.get("PASSWORD") or "KgPayout_Test_2026!").strip()
USDT_BALANCE = Decimal(os.environ.get("USDT_BALANCE", "50000") or "50000")
TOPUP_KGS = Decimal(os.environ.get("TOPUP_KGS", "0") or "0")
PS_NAMES = (C2C_KGS_PS_NAME, PHONE_KGS_PS_NAME, KGS_PS_NAME)


def _virtual_card() -> str:
    return ("5" + uuid.uuid4().hex[:15]).ljust(16, "0")[:16]


def ensure_ps_out_on(kgs: Currency) -> list[PaymentSystem]:
    out: list[PaymentSystem] = []
    for name in PS_NAMES:
        ps = PaymentSystem.objects.filter(name=name, currency=kgs).first()
        if ps is None:
            print(f"  ! PaymentSystem {name} missing — run shell_setup_melbet_kgs_prisma.py")
            continue
        fields: list[str] = []
        if not ps.out_on:
            ps.out_on = True
            fields.append("out_on")
        if fields:
            ps.save(update_fields=fields)
            print(f"  + {name} out_on=True")
        else:
            print(f"  ~ {name} out_on={ps.out_on}")
        out.append(ps)
    return out


def ensure_trader(kgs: Currency, payment_systems: list[PaymentSystem]) -> Trader:
    lang = Language.objects.order_by("id").first()
    traffic, _ = TrafficType.objects.get_or_create(name="Standard", defaults={"risk_level": 0})
    team, _ = TraderTeam.objects.get_or_create(name=TEAM_NAME)

    for ps in payment_systems:
        TraderTeamRates.objects.get_or_create(
            team=team,
            payment_system=ps,
            defaults={"mdr_in": MDR_IN, "mdr_out": MDR_OUT},
        )

    user = User.objects.filter(username=TRADER).first()
    if user is None:
        user = User.objects.create_user(
            username=TRADER,
            email=f"{TRADER}@test.local",
            password=PASSWORD,
        )
        print(f"  + user {TRADER} password={PASSWORD}")
    else:
        print(f"  ~ user {TRADER}")

    trader = Trader.objects.filter(user=user).select_related("balance_usdt", "team").first()
    if trader is None:
        trader = Trader.objects.create(
            user=user,
            team=team,
            currency=kgs,
            language=lang,
            balance_usdt=Balance.objects.create(type=0, amount=USDT_BALANCE),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
            is_boss=True,
            manual_mode=True,
            telegram=f"@{TRADER}",
            phone="+996700000001",
        )
        print(f"  + trader {TRADER}")
    else:
        fields = []
        if trader.team_id != team.id:
            trader.team = team
            fields.append("team")
        if trader.blocked:
            trader.blocked = False
            fields.append("blocked")
        if not trader.manual_mode:
            trader.manual_mode = True
            fields.append("manual_mode")
        if fields:
            trader.save(update_fields=fields)
        if trader.balance_usdt and trader.balance_usdt.amount < USDT_BALANCE:
            trader.balance_usdt.amount = USDT_BALANCE
            trader.balance_usdt.save(update_fields=["amount"])
        print(f"  ~ trader {TRADER}")

    for ps in payment_systems:
        group = PaymentDetailsGroup.objects.filter(
            trader=trader, payment_system=ps, currency=kgs
        ).first()
        if group is None:
            group = PaymentDetailsGroup.objects.create(
                owner=f"{TRADER} {ps.name} OUT",
                trader=trader,
                currency=kgs,
                payment_system=ps,
                status=1,
                amount=Decimal("999999"),
                in_active=False,
                out_active=True,
                min_amount_out=Decimal("1"),
                max_amount_out=Decimal("5000000"),
                work_type="by_card",
                deposit_number_on=False,
                auto_live=timezone.now(),
                current_volume=Decimal("0"),
                current_out_volume=Decimal("0"),
                limit_per_period=Decimal("999999999"),
            )
            group.allowed_traffic.add(traffic)
            print(f"    + group {ps.name} {group.id}")
        else:
            group.status = 1
            group.out_active = True
            group.in_active = False
            group.min_amount_out = Decimal("1")
            group.max_amount_out = Decimal("5000000")
            group.auto_live = timezone.now()
            group.save()
            group.allowed_traffic.add(traffic)
            print(f"    ~ group {ps.name} {group.id} out_active=True")

        detail = PaymentDetails.objects.filter(group=group, status=1).first()
        if detail is None:
            suffix = uuid.uuid4().int % 10**7
            kwargs = {
                "group": group,
                "status": 1,
                "amount": Decimal("999999"),
                "deposit_number": str(uuid.uuid4().int % 10**20).zfill(20),
                "sberpay_enabled": False,
                "sbp_enabled": False,
                "bank_name": "MBank",
                # choose_detail_out historically preferred card_number — keep one always.
                "card_number": _virtual_card(),
            }
            if ps.name.upper() in {"PHONEKGS", "QRKGS"}:
                kwargs["phone"] = f"+9967{suffix:07d}"
            if ps.name.upper() == "QRKGS":
                kwargs["qr_payload"] = "https://example.invalid/media/pd_qr/test.png"
            detail = PaymentDetails.objects.create(**kwargs)
            print(f"      + detail {detail.id}")
        else:
            changed = False
            if not (detail.card_number or "").strip():
                detail.card_number = _virtual_card()
                changed = True
            if not (detail.bank_name or "").strip():
                detail.bank_name = "MBank"
                changed = True
            if changed:
                detail.save()
            print(f"      ~ detail {detail.id}")

    print(f"  NOTE: не добавляйте {TRADER} в PSP_TRADER_USERNAMES")
    return trader


def maybe_topup_merchants() -> None:
    if TOPUP_KGS <= 0:
        return
    for uname in ("melbet", "melbet_test"):
        mu = User.objects.filter(username=uname).first()
        m = Merchant.objects.filter(user=mu).first() if mu else None
        if m is None:
            continue
        ensure_kgs_balances(m)
        m.refresh_from_db()
        if m.balance_kgs and m.balance_kgs.amount < TOPUP_KGS:
            m.balance_kgs.amount = TOPUP_KGS
            m.balance_kgs.save(update_fields=["amount"])
            print(f"  + {uname} balance_kgs={TOPUP_KGS}")
        else:
            print(f"  ~ {uname} balance_kgs={m.balance_kgs.amount if m.balance_kgs_id else 'n/a'}")


def run() -> None:
    print("=== Prep Melbet KGS payout acceptance ===")
    kgs = Currency.objects.filter(symbol="KGS").first()
    if kgs is None:
        print("ERROR: Currency KGS missing")
        return
    payment_systems = ensure_ps_out_on(kgs)
    if not payment_systems:
        return
    ensure_trader(kgs, payment_systems)
    maybe_topup_merchants()

    print("\nMelbet can now send test withdrawal, e.g.:")
    print('  currency=KGS  method=card2card_kgs  account_number=4400123456789012')
    print('  currency=KGS  method=phone_kgs      account_number=+996700123456')
    print("\nAfter create (In Progress), complete with:")
    print(
        f"  MERCHANT_ORDER_ID=<moid> APPLY=1 TRADER={TRADER} \\"
    )
    print(
        "  docker compose exec -T -e MERCHANT_ORDER_ID -e APPLY -e TRADER app \\"
    )
    print(
        "    python manage.py shell < titanpay/basics/shell_force_melbet_payout_success.py"
    )
    print("\n.env (pin payout trader for melbet):")
    print(
        f'  PAYOUT_PREFERRED_TRADER_BY_MERCHANT={{"melbet":"{TRADER}","melbet_test":"{TRADER}"}}'
    )


run()
