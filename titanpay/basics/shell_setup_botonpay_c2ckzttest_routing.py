"""
Тест BotonPay: отдельная PS C2CKZTTEST → только botonpay1 (без prod C2CKZT).

Создаёт:
  - PaymentSystem C2CKZTTEST (KZT)
  - виртуальную группу + реквизит у botonpay1
  - MerchantSolution у тестового мерчанта (по умолчанию melbet_test)

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_botonpay_c2ckzttest_routing.py

Проверка роутинга:
  docker compose exec -T app python manage.py diagnose_routing melbet_test --ps C2CKZTTEST --amount 50000 --ftd false

Pay-in (H2H): payment_system=C2CKZTTEST, currency=KZT, ftd=false

BotonPay sandbox: BOTONPAY_API_KEY=bp_test_... в .env

Локально прогнать success webhook (после реальной выдачи реквизитов):
  docker compose exec -T app python manage.py shell -c "
from basics.shell_setup_botonpay_c2ckzttest_routing import simulate_botonpay_success_webhook
simulate_botonpay_success_webhook('PAY_IN_UUID')
"
"""
from __future__ import annotations

import datetime
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
from merchant.models import Merchant, MerchantSolution
from payments.botonpay_client import botonpay_trader_username
from payments.models import BotonpayPayInSession
from payments.psp_payin import complete_inorder_from_psp_webhook, psp_trader_usernames
from trade.models import InOrder

PS_NAME = (getattr(settings, "BOTONPAY_TEST_PS_NAME", None) or "C2CKZTTEST").strip()
MERCHANT_USERNAME = "melbet_test"
TRAFFIC_NAME = "Standard"
TEAM_NAME = "BotonPay Agg"
GROUP_OWNER = "BotonPay C2CKZTTEST test"
LIMITS = {
    "min_limit_in": Decimal("1000"),
    "max_limit_in": Decimal("500000"),
    "min_limit_out": Decimal("1000"),
    "max_limit_out": Decimal("500000"),
}


def ensure_payment_system(kzt: Currency) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
    if ps:
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


def ensure_botonpay_virtual_group(trader: Trader, ps: PaymentSystem, kzt: Currency, traffic: TrafficType):
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
        print(f"  + virtual group {PS_NAME} ({group.id}) card …{card[-4:]}")
    else:
        changed = False
        for field, val in (
            ("status", 1),
            ("in_active", True),
            ("current_volume", Decimal("0")),
        ):
            if getattr(group, field) != val:
                setattr(group, field, val)
                changed = True
        if changed:
            group.save()
        detail = PaymentDetails.objects.filter(group=group, status=1).first()
        if detail is None:
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
            print(f"  ~ virtual group {PS_NAME} ({group.id}) card …{str(detail.card_number or '')[-4:]}")
    return group


def ensure_merchant_solution(merchant: Merchant, ps: PaymentSystem, traffic: TrafficType):
    merchant.payment_systems.add(ps)
    for ftd in (False, True):
        sol, created = MerchantSolution.objects.get_or_create(
            merchant=merchant,
            payment_system=ps,
            ftd=ftd,
            defaults={
                "status": 1,
                "traffic": traffic,
                "mdr_in": Decimal("2.5"),
                "mdr_out": Decimal("3.0"),
                "autoclose_arbitrage": False,
                **LIMITS,
            },
        )
        if not created:
            sol.status = 1
            sol.traffic = traffic
            sol.min_limit_in = LIMITS["min_limit_in"]
            sol.max_limit_in = LIMITS["max_limit_in"]
            sol.save(
                update_fields=[
                    "status",
                    "traffic",
                    "min_limit_in",
                    "max_limit_in",
                ]
            )
        tag = "+" if created else "~"
        print(f"  {tag} MerchantSolution ftd={ftd} ps={PS_NAME}")


def deactivate_other_psp_groups_on_test_ps(ps: PaymentSystem, *, keep_username: str) -> None:
    """C2CKZTTEST — только botonpay1; plutus1 и др. PSP отключаем (иначе роутинг берёт plutus первым)."""
    keep_trader = Trader.objects.filter(user__username=keep_username).first()
    qs = PaymentDetailsGroup.objects.filter(payment_system=ps, in_active=True).select_related(
        "trader__user"
    )
    if keep_trader:
        qs = qs.exclude(trader_id=keep_trader.id)
    psp_names = psp_trader_usernames()
    for group in qs:
        uname = group.trader.user.username if group.trader and group.trader.user else ""
        if uname in psp_names:
            group.in_active = False
            group.save(update_fields=["in_active"])
            print(f"  - deactivated C2CKZTTEST group {group.id} trader={uname}")


@transaction.atomic
def run(merchant_username: str = MERCHANT_USERNAME) -> None:
    print("=" * 60)
    print(f"BotonPay test routing: PS={PS_NAME} merchant={merchant_username}")
    print("=" * 60)

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        raise RuntimeError("Currency KZT not found")

    ps = ensure_payment_system(kzt)
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    trader_user = User.objects.filter(username=botonpay_trader_username()).first()
    if trader_user is None:
        raise RuntimeError(
            f"Trader user {botonpay_trader_username()!r} not found — "
            "run shell_create_botonpay_trader.py first"
        )
    trader = Trader.objects.filter(user=trader_user).select_related("team").first()
    if trader is None:
        raise RuntimeError(f"Trader {botonpay_trader_username()!r} not found")

    team = trader.team or TraderTeam.objects.filter(name=TEAM_NAME).first()
    if team is None:
        raise RuntimeError(f"Team {TEAM_NAME!r} not found")
    TraderTeamRates.objects.get_or_create(
        team=team,
        payment_system=ps,
        defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")},
    )

    if trader.balance_usdt.amount < Decimal("1000"):
        trader.balance_usdt.amount = Decimal("50000")
        trader.balance_usdt.save(update_fields=["amount"])
        print(f"  + topped balance_usdt for {botonpay_trader_username()}")

    ensure_botonpay_virtual_group(trader, ps, kzt, traffic)
    deactivate_other_psp_groups_on_test_ps(ps, keep_username=botonpay_trader_username())

    try:
        merchant = Merchant.objects.get(user__username=merchant_username)
    except Merchant.DoesNotExist:
        raise RuntimeError(
            f"Merchant {merchant_username!r} not found — создайте melbet_test или передайте другой username"
        )
    ensure_merchant_solution(merchant, ps, traffic)

    print("")
    print("Done.")
    print("  • .env: BOTONPAY_API_KEY=bp_test_... (sandbox) или bp_live_...")
    print("  • .env: BOTONPAY_WEBHOOK_SECRET=... + PUBLIC_API_URL")
    print(f"  • Pay-in: payment_system={PS_NAME}, currency=KZT")
    print("  • Webhook BotonPay: merchant_order_id = <PayIn UUID>")
    print(
        f"  • diagnose: python manage.py diagnose_routing {merchant_username} "
        f"--ps {PS_NAME} --amount 50000 --ftd false"
    )


def simulate_botonpay_success_webhook(pay_in_id: str, *, amount_fiat: str | None = None) -> None:
    """
    Имитация deal.completed (для проверки complete без ожидания BotonPay).
    Используйте только на тестовой заявке C2CKZTTEST.
    """
    from payments.models import PayIn

    pay_in = PayIn.objects.select_related("order", "payment_system").get(pk=pay_in_id)
    if pay_in.payment_system.name != PS_NAME:
        print(f"WARN: pay_in PS={pay_in.payment_system.name}, expected {PS_NAME}")

    session = BotonpayPayInSession.objects.filter(pay_in=pay_in).first()
    amount = amount_fiat or str(pay_in.amount)
    body = {
        "event": "deal.completed",
        "deal_uuid": session.provider_deal_uuid if session else str(uuid.uuid4()),
        "merchant_order_id": str(pay_in.id),
        "status": "completed",
        "status_version": 3,
        "fiat": "KZT",
        "amount_fiat": float(amount),
    }
    if session:
        session.last_webhook_payload = body
        session.last_notified_status = "completed"
        session.save(update_fields=["last_webhook_payload", "last_notified_status", "updated_at"])

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


run()
