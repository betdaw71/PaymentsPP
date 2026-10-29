"""
Plutus prod: осмотр plutus1 и включение групп C2CKZT/C2C (KZT).

Доля 10% — только .env (скрипт его не пишет):
  PSP_ROUTING_SHARE_MAP={"payplat1": 45, "gipay1": 20, "visionx1": 20, "layerone1": 5, "plutus1": 10}

Осмотр:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_plutus_ensure_prod.py

Включить группы + float:
  docker compose exec -T -e APPLY=1 app python manage.py shell < titanpay/basics/shell_plutus_ensure_prod.py

Трейдера нет:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_plutus_trader.py
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from django.conf import settings
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
from payments.plutus_client import plutus_trader_username
from payments.psp_payin import parse_routing_share_map
from titanpay.settings import C2C_NAME

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
SHARE_LINE = '{"payplat1": 45, "gipay1": 20, "visionx1": 20, "layerone1": 5, "plutus1": 10}'
GROUP_OWNER = "Plutus Virtual Drop"
TRAFFIC_NAME = "Standard"
PROD_PS = ("C2CKZT", C2C_NAME)
MIN_USDT = Decimal("1000")
PSP_FLOAT_USDT = Decimal("50000")
DEFAULT_MDR_IN = Decimal("7")


def _api_key_ok() -> bool:
    return bool((getattr(settings, "PLUTUS_API_KEY", None) or "").strip())


def _ensure_virtual_card(group: PaymentDetailsGroup) -> None:
    cards = PaymentDetails.objects.filter(
        group=group,
        status=1,
        sberpay_enabled=False,
        sbp_enabled=False,
        card_number__isnull=False,
    ).count()
    if cards:
        return
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
    print(f"    + virtual card for group {group.id}")


def ensure_group(trader: Trader, kzt: Currency, ps: PaymentSystem, traffic: TrafficType) -> PaymentDetailsGroup:
    group = PaymentDetailsGroup.objects.filter(
        trader=trader, payment_system=ps, currency=kzt
    ).first()
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
        )
        group.allowed_traffic.add(traffic)
        print(f"  + group {ps.name} ({group.id})")
    else:
        changed = False
        if group.status != 1:
            group.status = 1
            changed = True
        if not group.in_active:
            group.in_active = True
            changed = True
        if group.amount < Decimal("999999"):
            group.amount = Decimal("999999")
            changed = True
        if changed:
            group.save()
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ group {ps.name} ({group.id}) status={group.status} in_active={group.in_active}")
    _ensure_virtual_card(group)
    return group


def run() -> None:
    username = plutus_trader_username()
    share = parse_routing_share_map()
    print(f"=== Plutus prod ({username}) APPLY={int(APPLY)} ===")
    print(f"PLUTUS_API_BASE={getattr(settings, 'PLUTUS_API_BASE', '')}")
    print(f"PLUTUS_API_KEY set={int(_api_key_ok())}")
    print(f"PSP_ROUTING_SHARE_MAP now: { {k: str(v) for k, v in share.items()} or '{}' }")
    print(f"нужно в .env: PSP_ROUTING_SHARE_MAP={SHARE_LINE}")

    user = User.objects.filter(username=username).first()
    if user is None:
        print(f"ERROR: user {username!r} not found — run shell_create_plutus_trader.py")
        return
    trader = Trader.objects.filter(user=user).select_related("team", "balance_usdt").first()
    if trader is None:
        print(f"ERROR: trader {username!r} not found")
        return

    usdt = trader.balance_usdt.amount if trader.balance_usdt_id else Decimal("0")
    print(f"trader blocked={trader.blocked} team={trader.team.name if trader.team_id else None} USDT={usdt}")
    if usdt < MIN_USDT:
        print(f"WARN: USDT {usdt} < {MIN_USDT} — роутинг его не возьмёт")

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        print("ERROR: currency KZT not found")
        return
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    if APPLY:
        if trader.blocked:
            trader.blocked = False
            trader.save(update_fields=["blocked"])
            print("  + unblocked trader")
        if trader.balance_usdt_id and trader.balance_usdt.amount < PSP_FLOAT_USDT:
            trader.balance_usdt.amount = PSP_FLOAT_USDT
            trader.balance_usdt.save(update_fields=["amount"])
            print(f"  + USDT {PSP_FLOAT_USDT}")
        for ps_name in PROD_PS:
            ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
            if ps is None:
                print(f"  WARN: PaymentSystem {ps_name}+KZT missing — skip")
                continue
            if trader.team_id:
                TraderTeamRates.objects.get_or_create(
                    team=trader.team,
                    payment_system=ps,
                    defaults={"mdr_in": DEFAULT_MDR_IN, "mdr_out": Decimal("2.5")},
                )
            ensure_group(trader, kzt, ps, traffic)

    print("groups:")
    for g in PaymentDetailsGroup.objects.filter(trader=trader).select_related(
        "payment_system", "payment_system__currency"
    ):
        cur = g.payment_system.currency.symbol if g.payment_system and g.payment_system.currency_id else "?"
        cards = PaymentDetails.objects.filter(group=g, status=1).count()
        mark = "  <- prod" if g.payment_system and g.payment_system.name in PROD_PS and cur == "KZT" else ""
        print(
            f"  {g.payment_system.name:12} {cur:4} in_active={g.in_active} "
            f"status={g.status} cards={cards}{mark}"
        )

    weight = share.get(username.lower())
    if weight is None:
        print("WARN: plutus1 нет в SHARE — первый слот его не возьмёт")
    else:
        total = sum(share.values()) or Decimal("1")
        pct = (weight / total) * Decimal("100")
        print(f"share weight={weight} ≈ {pct:.1f}% of lottery")
    if not _api_key_ok():
        print("WARN: PLUTUS_API_KEY empty — create pay-in у Plutus упадёт")

    print("")
    print("после правки .env: docker compose up -d app")
    print("  python manage.py diagnose_routing mostbet --ps C2CKZT --amount 10000 --ftd false")


if not str(__name__).startswith("basics."):
    run()
