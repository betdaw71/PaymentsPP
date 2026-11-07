"""
Тест VisionX: C2CKZTTEST → только visionx1.

  - отключает все остальные реки на C2CKZTTEST
  - создаёт/включает виртуальную группу visionx1 на C2CKZTTEST
  - пополняет balance_usdt visionx1
  - MerchantSolution у lunatrixpay (или MERCHANT_USERNAME)

Прод C2C/C2CKZT у visionx1 не трогает.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_visionx_c2ckzttest_routing.py
"""
from __future__ import annotations

import datetime
import os
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from basics.models import (
    Currency,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeam,
    TraderTeamRates,
    TrafficType,
)
from basics.shell_merchant_solution import ensure_merchant_solution
from merchant.models import Merchant
from payments.psp_payin import complete_inorder_from_psp_webhook
from payments.visionx_client import visionx_trader_username
from trade.models import InOrder

PS_NAME = "C2CKZTTEST"
MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "lunatrixpay").strip()
TRAFFIC_NAME = "Standard"
TEAM_NAME = "VisionX KZT"
GROUP_OWNER = "VisionX C2CKZTTEST test"
PSP_FLOAT_USDT = Decimal("50000")
LIMITS = {
    "min_limit_in": Decimal("1000"),
    "max_limit_in": Decimal("500000"),
    "min_limit_out": Decimal("1000"),
    "max_limit_out": Decimal("500000"),
}


def ensure_payment_system(kzt: Currency) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
    if ps:
        if not ps.in_on:
            ps.in_on = True
            ps.save(update_fields=["in_on"])
        print(f"  ~ PaymentSystem {ps.name} ({ps.id})")
        return ps
    ps = PaymentSystem.objects.create(
        name=PS_NAME,
        currency=kzt,
        usdt_exchange_rate=Decimal("520"),
        expired_time_in=datetime.timedelta(minutes=15),
        expired_time_out=datetime.timedelta(minutes=10),
        confirm_time_out=datetime.timedelta(minutes=10),
        constrain_time_out=datetime.timedelta(hours=4),
        in_on=True,
        out_on=False,
        sbp_compatible=False,
        required_fields={
            "card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"},
            "owner": {"regex": r"^.+$", "pattern": "Card holder"},
            "bank": {"regex": r"^.+$", "pattern": "Bank"},
        },
    )
    print(f"  + PaymentSystem {ps.name} ({ps.id})")
    return ps


def ensure_visionx_virtual_group(trader: Trader, ps: PaymentSystem, kzt: Currency, traffic: TrafficType):
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=ps, currency=kzt).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner=GROUP_OWNER,
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
            limit_per_period=Decimal("999999999"),
        )
        group.allowed_traffic.add(traffic)
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
        print(f"  + virtual group {PS_NAME} ({group.id})")
        return group

    group.status = 1
    group.in_active = True
    group.current_volume = Decimal("0")
    group.limit_per_period = Decimal("999999999")
    group.auto_live = timezone.now()
    group.save(
        update_fields=["status", "in_active", "current_volume", "limit_per_period", "auto_live"]
    )
    group.allowed_traffic.add(traffic)
    if PaymentDetails.objects.filter(group=group, status=1).count() == 0:
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
        print(f"  + PaymentDetails on group {group.id}")
    else:
        print(f"  ~ virtual group {PS_NAME} ({group.id}) in_active=True")
    return group


def deactivate_other_groups_on_test_ps(ps: PaymentSystem, *, keep_username: str) -> None:
    keep_trader = Trader.objects.filter(user__username=keep_username).first()
    qs = PaymentDetailsGroup.objects.filter(payment_system=ps, in_active=True).select_related("trader__user")
    if keep_trader:
        qs = qs.exclude(trader_id=keep_trader.id)
    for group in qs:
        uname = group.trader.user.username if group.trader and group.trader.user else "?"
        group.in_active = False
        group.save(update_fields=["in_active"])
        print(f"  - deactivated C2CKZTTEST group {group.id} trader={uname}")


@transaction.atomic
def run(merchant_username: str = MERCHANT_USERNAME) -> None:
    keep = visionx_trader_username()
    print("=" * 60)
    print(f"VisionX test routing: PS={PS_NAME} merchant={merchant_username} → {keep} only")
    print("=" * 60)
    print(f"  VISIONX_API_BASE={getattr(settings, 'VISIONX_API_BASE', '')}")
    print(f"  VISIONX_API_KEY_set={bool(getattr(settings, 'VISIONX_API_KEY', ''))}")
    print(f"  VISIONX_PAYIN_OPTION={getattr(settings, 'VISIONX_PAYIN_OPTION', '')}")
    print(f"  VISIONX_PAYIN_OPTION_MAP={getattr(settings, 'VISIONX_PAYIN_OPTION_MAP', '')}")

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        raise RuntimeError("Currency KZT not found")

    ps = ensure_payment_system(kzt)
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    trader_user = User.objects.filter(username=keep).first()
    if trader_user is None:
        raise RuntimeError(f"Trader {keep!r} not found — run shell_create_visionx_trader.py first")
    trader = Trader.objects.filter(user=trader_user).select_related("team", "balance_usdt").first()
    if trader is None:
        raise RuntimeError(f"Trader record missing for {keep!r}")

    team = trader.team or TraderTeam.objects.filter(name=TEAM_NAME).first()
    if team is None:
        team, _ = TraderTeam.objects.get_or_create(
            name=TEAM_NAME, defaults={"rate_in": Decimal("5"), "rate_out": Decimal("2")}
        )
        trader.team = team
        trader.save(update_fields=["team"])
    TraderTeamRates.objects.get_or_create(
        team=team,
        payment_system=ps,
        defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")},
    )

    if trader.balance_usdt.amount < PSP_FLOAT_USDT:
        trader.balance_usdt.amount = PSP_FLOAT_USDT
        trader.balance_usdt.save(update_fields=["amount"])
        print(f"  + topped balance_usdt to {PSP_FLOAT_USDT} for {keep}")
    else:
        print(f"  ~ balance_usdt={trader.balance_usdt.amount} for {keep}")

    ensure_visionx_virtual_group(trader, ps, kzt, traffic)
    deactivate_other_groups_on_test_ps(ps, keep_username=keep)

    try:
        merchant = Merchant.objects.get(user__username=merchant_username)
    except Merchant.DoesNotExist as exc:
        raise RuntimeError(f"Merchant {merchant_username!r} not found") from exc

    ensure_merchant_solution(merchant, ps, traffic, overwrite_limits=True, limits=LIMITS)

    print("\nDone.")
    print(f"  • {keep}: active C2CKZTTEST, other C2CKZTTEST groups off")
    print(f"  • diagnose: diagnose_routing {merchant_username} --ps {PS_NAME} --amount 7000 --ftd false")
    print("  • create: env TEST_AMOUNT=7000 shell_create_lunatrix_c2ckzttest_payin_page.py")


def dump_last_visionx_session():
    from payments.models import VisionxPayInSession
    from payments.visionx_client import visionx_map_requisite

    s = VisionxPayInSession.objects.select_related("pay_in").order_by("-updated_at").first()
    if s is None:
        print("no VisionxPayInSession")
        return
    pay_in = s.pay_in
    order = pay_in.order if pay_in else None
    trader = None
    if order and order.payment_details and order.payment_details.group and order.payment_details.group.trader:
        trader = order.payment_details.group.trader.user.username
    print("pay_in", pay_in.id if pay_in else None)
    print("pay_in.status", pay_in.status.name if pay_in and pay_in.status else None)
    print("trader", trader)
    print("invoice", s.provider_invoice_id, "deal", s.provider_deal_id)
    print("mapped", visionx_map_requisite(s.create_response or {}))
    err = (s.create_response or {}).get("error") if isinstance(s.create_response, dict) else None
    if err:
        print("create_error", err, s.create_response)


def simulate_visionx_success_webhook(pay_in_id: str) -> None:
    from payments.models import PayIn, VisionxPayInSession

    pay_in = PayIn.objects.select_related("order", "payment_system").get(pk=pay_in_id)
    session = VisionxPayInSession.objects.filter(pay_in=pay_in).first()
    body = {
        "invoice": {
            "id": (session.provider_invoice_id if session else "") or str(uuid.uuid4()),
            "internalId": str(pay_in.id),
            "status": "paid",
            "amount": str(pay_in.amount),
            "currency": "KZT",
        }
    }
    if session:
        session.last_webhook_payload = body
        session.last_notified_state = "paid"
        session.save(update_fields=["last_webhook_payload", "last_notified_state", "updated_at"])
    order = pay_in.order
    if order is None:
        raise RuntimeError("PayIn has no InOrder")
    with transaction.atomic():
        locked = InOrder.objects.select_for_update().get(pk=order.pk)
        if locked.status and locked.status.name == "Completed":
            print("Already Completed")
            return
        complete_inorder_from_psp_webhook(locked, body)
    pay_in.refresh_from_db()
    order.refresh_from_db()
    print(f"OK PayIn={pay_in.id} PayIn.status={pay_in.status.name} InOrder={order.status.name}")


if not str(__name__).startswith("basics."):
    run()
