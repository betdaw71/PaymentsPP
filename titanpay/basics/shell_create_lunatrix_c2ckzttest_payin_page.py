"""
Создать тестовый pay-in lunatrixpay / C2CKZTTEST и вывести ссылку на платёжную страницу.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_lunatrix_c2ckzttest_payin_page.py

Перед этим:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_setup_lunatrix_kzt_c2ckzttest_appeal.py
  docker compose exec -T app python manage.py diagnose_routing lunatrixpay --ps C2CKZTTEST --amount 10002 --ftd false
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from merchant.models import Merchant, MerchantSolution
from payments.models import PayIn, PayInStatus
from payments.psp_payin import decline_payin
from payments.utils import generate_link
from payments.utils2 import assert_payin_amount_within_solution, get_client_object
from trade.models import InOrder

MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "lunatrixpay").strip()
PS_NAME = os.environ.get("TEST_PS_NAME", "C2CKZTTEST").strip()
AMOUNT = Decimal(os.environ.get("TEST_AMOUNT", "10002"))


@transaction.atomic
def run() -> None:
    merchant = Merchant.objects.get(user__username=MERCHANT_USERNAME)
    sol = MerchantSolution.objects.get(
        merchant=merchant,
        payment_system__name=PS_NAME,
        ftd=False,
        status=1,
    )
    assert_payin_amount_within_solution(sol, AMOUNT)

    moid = f"page-test-{uuid.uuid4().hex[:10]}"
    client, ok = get_client_object({"client_id": f"c-{uuid.uuid4().hex[:8]}"}, merchant)
    if not ok:
        raise RuntimeError("client blacklisted")

    in_order = InOrder.create(
        amount=AMOUNT,
        solution=sol,
        client_deposit_count=client.order_count,
        merchant_order_id=moid,
    )
    print("in_order:", in_order.id)
    print("in_order status:", in_order.status.name)

    if in_order.status.name == "Cannot process":
        pay_in = PayIn.objects.create(
            amount=AMOUNT,
            currency=sol.payment_system.currency,
            payment_system=sol.payment_system,
            merchant_order_id=moid,
            callback_url="https://example.invalid/test",
            merchant=merchant,
            order=in_order,
            status=PayInStatus.objects.get(name="In Progress"),
            client=client,
        )
        decline_payin(pay_in, send_callback=False)
        active = InOrder.objects.filter(
            status__name__in=["New", "Money sent by user"],
            amount=AMOUNT,
            solution__payment_system=sol.payment_system,
        ).exclude(pk=in_order.pk)
        print("ERROR: routing failed — Cannot process")
        if active.exists():
            print(f"  likely cause: {active.count()} active order(s) on same amount {AMOUNT} block the card")
            for o in active[:5]:
                print(f"    stuck: {o.id} status={o.status.name} moid={o.merchant_order_id}")
            print(f"  try: TEST_AMOUNT={AMOUNT + 1} or expire/cancel stuck orders")
        else:
            print("  likely cause: USDT freeze failed or no free card in group")
        print("PayIn declined:", pay_in.id)
        return

    pay_in = PayIn.objects.create(
        amount=AMOUNT,
        currency=sol.payment_system.currency,
        payment_system=sol.payment_system,
        merchant_order_id=moid,
        callback_url="https://example.invalid/test",
        merchant=merchant,
        order=in_order,
        status=PayInStatus.objects.get(name="In Progress"),
        client=client,
    )

    pd = in_order.payment_details
    if pd:
        print("trader:", pd.group.trader.user.username)
        print("card:", pd.card_number)

    print("pay_in_id:", pay_in.id)
    print("payment page:", generate_link(pay_in.id, pay_in.payment_system.name))


if User.objects.filter(username=MERCHANT_USERNAME).exists():
    run()
else:
    print(f"Merchant {MERCHANT_USERNAME} not found")
