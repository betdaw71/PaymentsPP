"""
Создать тестовый pay-in lunatrixpay / C2CKZTTEST через Plutus (plutus1).

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_lunatrix_plutus_c2ckzttest_payin.py

Перед этим:
  shell_create_plutus_trader.py
  shell_setup_lunatrix_plutus_c2ckzttest_routing.py

Суммы (мин. MerchantSolution обычно 1000 KZT):
  TEST_AMOUNT=5000
  TEST_AMOUNTS=5000,10000,15000,3000

Sandbox Plutus (ключ th_sandbox_...): сумма 100, но min lunatrix = 1000 —
  временно: MIN_LIMIT_IN=100 в shell_setup или TEST_AMOUNTS после понижения лимита.
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
from payments.psp_payin import try_attach_psp_sessions
from payments.utils import generate_link
from payments.utils2 import assert_payin_amount_within_solution, get_client_object
from trade.models import InOrder

MERCHANT_USERNAME = os.environ.get("MERCHANT_USERNAME", "lunatrixpay").strip()
PS_NAME = os.environ.get("TEST_PS_NAME", "C2CKZTTEST").strip()


def _candidate_amounts(sol: MerchantSolution) -> list[Decimal]:
    raw = (os.environ.get("TEST_AMOUNTS") or os.environ.get("TEST_AMOUNT") or "5000,10000,15000,3000").strip()
    out: list[Decimal] = []
    seen: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if part in seen:
            continue
        seen.add(part)
        amt = Decimal(part)
        if sol.min_limit_in <= amt <= sol.max_limit_in:
            out.append(amt)
        else:
            print(f"  skip amount {amt} (limits {sol.min_limit_in}..{sol.max_limit_in})")
    return out


def _plutus_error_message(cr: dict) -> str:
    if not isinstance(cr, dict):
        return str(cr)
    platform = cr.get("platform")
    if isinstance(platform, dict):
        msg = platform.get("message") or platform.get("code")
        if msg:
            return str(msg)
    if cr.get("code"):
        return str(cr["code"])
    if cr.get("error"):
        return str(cr["error"])
    return "unknown"


@transaction.atomic
def _attempt(amount: Decimal, merchant: Merchant, sol: MerchantSolution) -> tuple[PayIn | None, str | None]:
    assert_payin_amount_within_solution(sol, amount)
    moid = f"lunatrix-plutus-{uuid.uuid4().hex[:10]}"
    client, ok = get_client_object({"client_id": f"c-{uuid.uuid4().hex[:8]}"}, merchant)
    if not ok:
        raise RuntimeError("client blacklisted")

    in_order = InOrder.create(
        amount=amount,
        solution=sol,
        client_deposit_count=client.order_count,
        merchant_order_id=moid,
    )
    if in_order.status.name == "Cannot process":
        return None, "routing Cannot process"

    trader_name = (
        in_order.payment_details.group.trader.user.username
        if in_order.payment_details and in_order.payment_details.group
        else "?"
    )
    if trader_name != plutus_trader_username():
        return None, f"routed {trader_name}, expected {plutus_trader_username()}"

    pay_in = PayIn.objects.create(
        amount=amount,
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

    session = PlutusPayInSession.objects.filter(pay_in=pay_in).first()
    if session is None:
        return pay_in, "no PlutusPayInSession (PLUTUS_API_KEY?)"

    cr = session.create_response or {}
    req = plutus_map_requisite(cr)
    if pay_in.status and pay_in.status.name == "Declined":
        return pay_in, _plutus_error_message(cr)
    if not req:
        return pay_in, _plutus_error_message(cr) or "empty requisites"
    return pay_in, None


def run() -> None:
    merchant = Merchant.objects.get(user__username=MERCHANT_USERNAME)
    sol = MerchantSolution.objects.get(
        merchant=merchant,
        payment_system__name=PS_NAME,
        ftd=False,
        status=1,
    )
    amounts = _candidate_amounts(sol)
    if not amounts:
        print(f"ERROR: no amounts in solution limits [{sol.min_limit_in}..{sol.max_limit_in}]")
        return

    print(f"limits: {sol.min_limit_in}..{sol.max_limit_in} KZT")
    print(f"try amounts: {', '.join(str(a) for a in amounts)}")

    last_pay_in = None
    last_err = None
    for amount in amounts:
        print(f"\n--- amount {amount} ---")
        pay_in, err = _attempt(amount, merchant, sol)
        last_pay_in = pay_in
        last_err = err
        if err:
            print(f"FAIL: {err}")
            if pay_in:
                print(f"  pay_in_id={pay_in.id} (declined)")
            continue

        in_order = pay_in.order
        session = PlutusPayInSession.objects.get(pay_in=pay_in)
        req = plutus_map_requisite(session.create_response or {})
        print("OK")
        print("in_order:", in_order.id, in_order.status.name)
        print("routed trader:", plutus_trader_username())
        print("plutus external_id:", session.external_id)
        print("plutus trade_id:", session.provider_trade_uuid or "—")
        print("requisites:", json.dumps(req, ensure_ascii=False, indent=2))
        print("pay_in_id:", pay_in.id)
        print("payment page:", generate_link(pay_in.id, pay_in.payment_system.name))
        print("diagnose:", f"python manage.py diagnose_payin {pay_in.id}")
        return

    print("\nERROR: Plutus did not allocate requisites for any tried amount.")
    if last_err:
        print(f"  last error: {last_err}")
    if last_pay_in:
        print(f"  last pay_in: {last_pay_in.id}")
        print(f"  diagnose: python manage.py diagnose_payin {last_pay_in.id}")
    print("\nЧто проверить на стороне Plutus:")
    print("  • В ЛК включён поток KZT / c2c и есть свободные реквизиты")
    print("  • PLUTUS_API_KEY — боевой или th_sandbox_... для sandbox")
    print("  • PLUTUS_PAYMETHOD_MAP: {\"C2CKZTTEST\":\"c2c\"} или нужный paymethod от Plutus")
    print("  • Попробуйте PLUTUS_CONTRAGENT=true в .env и перезапуск app")


if User.objects.filter(username=MERCHANT_USERNAME).exists():
    run()
else:
    print(f"Merchant {MERCHANT_USERNAME} not found")
