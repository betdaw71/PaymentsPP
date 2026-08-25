"""
Создать тестовый pay-in lunatrixpay / C2CKZTTEST через Plutus (plutus1).

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_lunatrix_plutus_c2ckzttest_payin.py

Перед этим:
  shell_create_plutus_trader.py
  shell_setup_lunatrix_plutus_c2ckzttest_routing.py
  diagnose_routing lunatrixpay --ps C2CKZTTEST --amount 100 --ftd false

Sandbox: TEST_AMOUNT=100 (автоколбек Plutus ~5 с при th_sandbox_... ключе).
"""
from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from merchant.models import Merchant, MerchantSolution
from payments.models import PayIn, PayInStatus, PlutusPayInSession
from payments.plutus_client import plutus_map_requisite, plutus_trader_username
from payments.psp_payin import decline_payin, try_attach_psp_sessions
from payments.utils import generate_link
from payments.utils2 import assert_payin_amount_within_solution, get_client_object
from trade.models import InOrder

MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "lunatrixpay").strip()
PS_NAME = os.environ.get("TEST_PS_NAME", "C2CKZTTEST").strip()
AMOUNT = Decimal(os.environ.get("TEST_AMOUNT", "100"))


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

    moid = f"lunatrix-plutus-{uuid.uuid4().hex[:10]}"
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
        print("ERROR: routing failed before PayIn — run shell_setup_lunatrix_plutus_c2ckzttest_routing.py")
        return

    trader_name = (
        in_order.payment_details.group.trader.user.username
        if in_order.payment_details and in_order.payment_details.group
        else "?"
    )
    print("routed trader:", trader_name)
    if trader_name != plutus_trader_username():
        print(f"WARN: expected {plutus_trader_username()}, got {trader_name}")

    pay_in = PayIn.objects.create(
        amount=AMOUNT,
        currency=sol.payment_system.currency,
        payment_system=sol.payment_system,
        merchant_order_id=moid,
        callback_url="https://example.invalid/lunatrix-plutus-test",
        merchant=merchant,
        order=in_order,
        status=PayInStatus.objects.get(name="In Progress"),
        client=client,
    )

    try_attach_psp_sessions(pay_in)
    pay_in.refresh_from_db()
    in_order.refresh_from_db()

    print("in_order status after PSP:", in_order.status.name)
    print("pay_in status:", pay_in.status.name if pay_in.status else None)

    session = PlutusPayInSession.objects.filter(pay_in=pay_in).first()
    if session is None:
        print("ERROR: no PlutusPayInSession — check PLUTUS_API_KEY and routing")
        if pay_in.status and pay_in.status.name != "Declined":
            decline_payin(pay_in, send_callback=False)
        return

    cr = session.create_response or {}
    req = plutus_map_requisite(cr)
    print("plutus external_id:", session.external_id)
    print("plutus trade_id:", session.provider_trade_uuid or "—")
    if isinstance(cr, dict) and cr.get("error"):
        print("plutus error:", cr.get("error"))
    print("requisites:", json.dumps(req, ensure_ascii=False, indent=2) if req else "(empty)")

    if pay_in.status and pay_in.status.name == "Declined":
        print("ERROR: PayIn declined — diagnose:")
        print(f"  python manage.py diagnose_payin {pay_in.id}")
        return

    if not req:
        print("ERROR: Plutus returned no requisites")
        print(f"  python manage.py diagnose_payin {pay_in.id}")
        return

    print("pay_in_id:", pay_in.id)
    print("payment page:", generate_link(pay_in.id, pay_in.payment_system.name))
    print("diagnose:", f"python manage.py diagnose_payin {pay_in.id}")
    print("simulate success:")
    print(
        "  from basics.shell_setup_plutus_c2ckzttest_routing import simulate_plutus_success_webhook"
    )
    print(f"  simulate_plutus_success_webhook('{pay_in.id}')")


if User.objects.filter(username=MERCHANT_USERNAME).exists():
    run()
else:
    print(f"Merchant {MERCHANT_USERNAME} not found")
