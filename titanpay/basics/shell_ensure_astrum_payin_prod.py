"""Astrum (astrum_kzt / «asterisk»): KZT pay-in группы + MDR 6% + осмотр.

Внимание: create pay-in к Astrum (try_attach) в коде ещё не подключён —
есть только webhook. Этот скрипт готовит трейдера/группы/ставки.
Полная выдача реквизитов потребует API /source/deal.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_ensure_astrum_payin_prod.py

  APPLY=1 — in_active=True, status=1, mdr_in=6.00, float USDT
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from django.conf import settings
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
from payments.astrum_client import astrum_trader_username

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
TARGET_MDR = Decimal(str(os.environ.get("MDR") or "6.00"))
PROD_PS = tuple(
    p.strip() for p in (os.environ.get("PS") or "C2CKZT,C2C").split(",") if p.strip()
)
TRAFFIC_NAME = "Standard"
PSP_FLOAT_USDT = Decimal("50000")
GROUP_OWNER = "Astrum KZT pay-in"


def _ensure_card(group: PaymentDetailsGroup) -> None:
    if PaymentDetails.objects.filter(
        group=group, status=1, card_number__isnull=False, sberpay_enabled=False, sbp_enabled=False
    ).exists():
        return
    card = "4" + uuid.uuid4().hex[:15]
    card = "".join(c for c in card if c.isdigit())[:16].ljust(16, "0")
    PaymentDetails.objects.create(
        group=group,
        status=1,
        amount=Decimal("9999999"),
        card_number=card,
        deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
        sberpay_enabled=False,
        sbp_enabled=False,
    )
    print(f"    + stub card ****{card[-4:]}")


def run() -> None:
    username = (os.environ.get("TRADER_USERNAME") or astrum_trader_username() or "astrum_kzt").strip()
    print(f"=== Astrum pay-in ensure ({username}) APPLY={int(APPLY)} mdr→{TARGET_MDR} ===")
    print(f"FX: поставь в .env PSP_XE_MARKUP_BY_TRADER … \"astrum_kzt\":\"1.03\"")
    print(
        "Каскад (низкий приоритет): в PSP_ROUTING_PRIORITY_MAP astrum_kzt=9 "
        "(после основных, до хвоста)"
    )

    trader = (
        Trader.objects.filter(user__username__iexact=username)
        .select_related("user", "team", "balance_usdt")
        .first()
    )
    if trader is None:
        print(f"! trader {username} not found — сначала shell_create_astrum_trader.py")
        return

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        print("! no KZT currency")
        return
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    if APPLY and trader.blocked:
        trader.blocked = False
        trader.save(update_fields=["blocked"])
        print("  + unblocked")
    if APPLY and trader.balance_usdt_id and trader.balance_usdt.amount < PSP_FLOAT_USDT:
        trader.balance_usdt.amount = PSP_FLOAT_USDT
        trader.balance_usdt.save(update_fields=["amount"])
        print(f"  + USDT float {PSP_FLOAT_USDT}")

    for ps_name in PROD_PS:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
        if ps is None:
            print(f"  ! PS {ps_name} missing")
            continue
        if trader.team_id:
            rate, created = TraderTeamRates.objects.get_or_create(
                team=trader.team,
                payment_system=ps,
                defaults={"mdr_in": TARGET_MDR, "mdr_out": Decimal("2.5")},
            )
            if not created and rate.mdr_in != TARGET_MDR:
                print(f"  {ps_name}: mdr {rate.mdr_in}% → {TARGET_MDR}%")
                if APPLY:
                    rate.mdr_in = TARGET_MDR
                    rate.save(update_fields=["mdr_in"])
            else:
                print(f"  {ps_name}: mdr={rate.mdr_in}%")

        group = PaymentDetailsGroup.objects.filter(
            trader=trader, payment_system=ps, currency=kzt
        ).first()
        if group is None:
            if not APPLY:
                print(f"  {ps_name}: no group (dry-run)")
                continue
            group = PaymentDetailsGroup.objects.create(
                owner=f"{GROUP_OWNER} {ps_name}",
                trader=trader,
                currency=kzt,
                payment_system=ps,
                status=1,
                amount=Decimal("9999999"),
                in_active=True,
                out_active=True,
                work_type="by_card",
                deposit_number_on=False,
                auto_live=timezone.now(),
                limit_per_period=Decimal("50000000"),
            )
            group.allowed_traffic.add(traffic)
            print(f"  + group {ps_name} {group.id}")
        else:
            print(
                f"  ~ group {ps_name} status={group.status} "
                f"in_active={group.in_active} out_active={group.out_active}"
            )
            if APPLY:
                changed = []
                if group.status != 1:
                    group.status = 1
                    changed.append("status")
                if not group.in_active:
                    group.in_active = True
                    changed.append("in_active")
                if changed:
                    group.auto_live = timezone.now()
                    group.save()
                    print(f"    + set {changed}")
                if not group.allowed_traffic.filter(pk=traffic.pk).exists():
                    group.allowed_traffic.add(traffic)
        if APPLY and group is not None:
            _ensure_card(group)

    markup = getattr(settings, "PSP_XE_MARKUP_BY_TRADER", "")
    print(f"\nPSP_XE_MARKUP_BY_TRADER={markup}")
    print(
        "NOTE: try_attach_astrum_session для pay-in ещё нет — "
        "после APPLY группы готовы, но каскад не получит реквизит от Astrum API "
        "пока не подключим POST /source/deal."
    )
    print("DONE")


run()
