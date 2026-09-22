"""
Тестовая выплата lunatrixpay как Mostbet: C2C KZT → remap C2CKZT → payplat1.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_lunatrix_mostbet_payout.py

Опционально:
  TEST_AMOUNT=20000
  TEST_CARD=4400430182839018
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIRequestFactory

from basics.models import PaymentDetails, PaymentDetailsGroup, PaymentSystem, Trader
from merchant.models import Merchant, MerchantSolution
from payments.models import PayplatPayOutSession
from payments.serializers import PayOutPaymentCreateSerializer
from titanpay.settings import C2CKZT_NAME as SETTINGS_C2CKZT
from titanpay.settings import PAYPLAT_TRADER_USERNAME

MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "lunatrixpay").strip() or "lunatrixpay"
PAYPLAT_USERNAME = PAYPLAT_TRADER_USERNAME or "payplat1"
C2CKZT_NAME = SETTINGS_C2CKZT or "C2CKZT"
AMOUNT = Decimal(os.environ.get("TEST_AMOUNT", "20000"))
CARD = "".join(c for c in os.environ.get("TEST_CARD", "4400430182839018") if c.isdigit())[:16].ljust(16, "0")


def _print_sol(label, sol):
    if sol is None:
        print(f"  {label}: MISSING")
        return
    traffic = sol.traffic.name if sol.traffic else "?"
    print(
        f"  {label}: status={sol.status} ftd={sol.ftd} traffic={traffic} "
        f"out=[{sol.min_limit_out} .. {sol.max_limit_out}] mdr_out={sol.mdr_out}"
    )


def _clone_solution(merchant, target_ps, sources):
    existing = MerchantSolution.objects.filter(
        merchant=merchant, payment_system=target_ps, ftd=False, status=1
    ).first()
    if existing is not None:
        return existing
    source = None
    for ps in sources:
        if ps is None:
            continue
        source = MerchantSolution.objects.filter(
            merchant=merchant, payment_system=ps, ftd=False
        ).order_by("-status").first()
        if source is not None:
            break
    if source is None:
        return None
    return MerchantSolution.objects.create(
        merchant=merchant,
        payment_system=target_ps,
        status=1,
        ftd=False,
        mdr_in=source.mdr_in,
        mdr_out=source.mdr_out,
        traffic=source.traffic,
        autoclose_arbitrage=source.autoclose_arbitrage,
        min_limit_in=source.min_limit_in,
        max_limit_in=source.max_limit_in,
        min_limit_out=min(source.min_limit_out or Decimal("1000"), Decimal("1000")),
        max_limit_out=max(source.max_limit_out or Decimal("0"), Decimal("500000")),
    )


def _ensure_payplat_out(c2ckzt, traffic):
    plat_user = User.objects.filter(username=PAYPLAT_USERNAME).first()
    payplat = Trader.objects.filter(user=plat_user).first() if plat_user else None
    if payplat is None:
        raise SystemExit(f"Trader {PAYPLAT_USERNAME} not found")
    if payplat.blocked:
        payplat.blocked = False
        payplat.save(update_fields=["blocked"])
        print(f"  ~ unblocked {PAYPLAT_USERNAME}")
    groups = PaymentDetailsGroup.objects.filter(trader=payplat, payment_system=c2ckzt)
    if not groups.exists():
        raise SystemExit(f"no C2CKZT group on {PAYPLAT_USERNAME}")
    for group in groups:
        changed = []
        if group.status != 1:
            group.status = 1
            changed.append("status")
        if not group.out_active:
            group.out_active = True
            changed.append("out_active")
        if group.deposit_number_on:
            group.deposit_number_on = False
            changed.append("deposit_number_on")
        if group.min_amount_out > AMOUNT:
            group.min_amount_out = Decimal("1000")
            changed.append("min_amount_out")
        if group.max_amount_out < AMOUNT:
            group.max_amount_out = Decimal("5000000")
            changed.append("max_amount_out")
        if (group.amount or Decimal("0")) < AMOUNT:
            group.amount = Decimal("9999999")
            changed.append("amount")
        group.auto_live = timezone.now()
        changed.append("auto_live")
        if changed:
            group.save()
            print(f"  ~ payplat group {group.id} {changed}")
        if traffic and not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        cards = PaymentDetails.objects.filter(group=group, status=1, card_number__isnull=False).count()
        print(f"  ~ payplat group {group.id} out_active={group.out_active} cards={cards}")
    return payplat


def run():
    print(f"=== lunatrixpay payout like Mostbet: C2C {AMOUNT} KZT → C2CKZT → {PAYPLAT_USERNAME} ===")
    settings.PAYOUT_C2C_TO_C2CKZT_MERCHANTS = f"mostbet,{MERCHANT_USERNAME}"
    settings.PAYOUT_PREFERRED_TRADER_BY_MERCHANT = (
        f'{{"mostbet":"{PAYPLAT_USERNAME}","{MERCHANT_USERNAME}":"{PAYPLAT_USERNAME}"}}'
    )

    user = User.objects.filter(username=MERCHANT_USERNAME).first()
    merchant = Merchant.objects.filter(user=user).first() if user else None
    if merchant is None:
        raise SystemExit(f"Merchant {MERCHANT_USERNAME} not found")

    kzt_c2c = PaymentSystem.objects.filter(name="C2C", currency__symbol="KZT").first()
    c2ckzt = PaymentSystem.objects.filter(name=C2CKZT_NAME, currency__symbol="KZT").first()
    test_ps = PaymentSystem.objects.filter(name="C2CKZTTEST").first()
    if c2ckzt is None:
        raise SystemExit(f"PaymentSystem {C2CKZT_NAME} not found")

    c2c_sol = _clone_solution(merchant, kzt_c2c, [kzt_c2c, c2ckzt, test_ps]) if kzt_c2c else None
    c2ckzt_sol = _clone_solution(merchant, c2ckzt, [c2ckzt, kzt_c2c, test_ps])
    _print_sol("C2C", c2c_sol)
    _print_sol("C2CKZT", c2ckzt_sol)
    if c2ckzt_sol is None:
        raise SystemExit("Cannot create C2CKZT MerchantSolution for lunatrixpay")
    if not (c2ckzt_sol.min_limit_out <= AMOUNT <= c2ckzt_sol.max_limit_out):
        c2ckzt_sol.min_limit_out = min(c2ckzt_sol.min_limit_out, AMOUNT)
        c2ckzt_sol.max_limit_out = max(c2ckzt_sol.max_limit_out, AMOUNT)
        c2ckzt_sol.save(update_fields=["min_limit_out", "max_limit_out"])
        print(f"  ~ C2CKZT out limits → [{c2ckzt_sol.min_limit_out} .. {c2ckzt_sol.max_limit_out}]")
    if c2c_sol and not (c2c_sol.min_limit_out <= AMOUNT <= c2c_sol.max_limit_out):
        c2c_sol.min_limit_out = min(c2c_sol.min_limit_out, AMOUNT)
        c2c_sol.max_limit_out = max(c2c_sol.max_limit_out, AMOUNT)
        c2c_sol.save(update_fields=["min_limit_out", "max_limit_out"])

    if not merchant.payment_systems.filter(pk=c2ckzt.pk).exists():
        merchant.payment_systems.add(c2ckzt)
    if kzt_c2c and not merchant.payment_systems.filter(pk=kzt_c2c.pk).exists():
        merchant.payment_systems.add(kzt_c2c)

    _ensure_payplat_out(c2ckzt, c2ckzt_sol.traffic)

    if merchant.balance is None or merchant.balance.amount < Decimal("500"):
        from basics.models import Balance

        if merchant.balance is None:
            merchant.balance = Balance.objects.create(type=0, amount=Decimal("10000"))
            merchant.save(update_fields=["balance"])
        else:
            merchant.balance.amount = Decimal("10000")
            merchant.balance.save(update_fields=["amount"])
        print(f"  ~ merchant USDT balance={merchant.balance.amount}")
    else:
        print(f"  merchant USDT balance={merchant.balance.amount}")

    payload = {
        "amount": str(AMOUNT),
        "currency": "KZT",
        "payment_system": "C2C",
        "merchant_order_id": f"lunatrix-mostbet-out-{uuid.uuid4().hex[:10]}",
        "callback_url": "https://example.invalid/lunatrix-payout",
        "ftd": False,
        "client": {
            "client_id": f"lunatrix-payout-{uuid.uuid4().hex[:8]}",
            "name": "Mostbet Test Client",
        },
        "details": {
            "card_number": CARD,
            "owner": "TEST MOSTBET",
            "bank": "Kaspi",
        },
    }
    print("  request payment_system=C2C (Mostbet style)")

    factory = APIRequestFactory()
    request = factory.post("/api/v1/payments/out/h2h/", payload, format="json")
    request.user = user
    serializer = PayOutPaymentCreateSerializer(data=payload, context={"request": request})
    serializer.is_valid(raise_exception=True)
    pay_out = serializer.save()
    pay_out.refresh_from_db()
    order = pay_out.order
    trader_name = None
    if order and order.payment_details and order.payment_details.group.trader:
        trader_name = order.payment_details.group.trader.user.username

    print(f"  pay_out={pay_out.id}")
    print(f"  merchant_order_id={pay_out.merchant_order_id}")
    print(f"  stored payment_system={pay_out.payment_system.name if pay_out.payment_system else None}")
    print(f"  pay_out.status={pay_out.status.name if pay_out.status else None}")
    print(f"  out_order.status={order.status.name if order and order.status else None}")
    print(f"  trader={trader_name}")
    print(f"  amount={pay_out.amount} usd_amount={order.usd_amount if order else None}")

    session = PayplatPayOutSession.objects.filter(pay_out=pay_out).first()
    if session is None:
        print("  PayplatPayOutSession: MISSING")
    else:
        print(f"  payplat session external_id={session.external_id} provider_payout_id={session.provider_payout_id}")
        print(f"  payplat create_response={session.create_response}")

    token, _ = Token.objects.get_or_create(user=user)
    print("")
    print("HTTP как Mostbet (после env PAYOUT_* lunatrixpay):")
    print(f"  POST /api/v1/payments/out/h2h/")
    print(f"  Authorization: Token {token.key}")
    print(f"  body payment_system=C2C currency=KZT amount={AMOUNT} details.card_number={CARD}")
    if trader_name == PAYPLAT_USERNAME and pay_out.payment_system and pay_out.payment_system.name == C2CKZT_NAME:
        print("Done. C2C remapped to C2CKZT and sent to PayPlat.")
    else:
        print(
            f"  ! expected trader={PAYPLAT_USERNAME} and PS={C2CKZT_NAME}. "
            "Check payplat out_active and PAYOUT_PREFERRED_TRADER_BY_MERCHANT."
        )


if not str(__name__).startswith("basics."):
    run()
