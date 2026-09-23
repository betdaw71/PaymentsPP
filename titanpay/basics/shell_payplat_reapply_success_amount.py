"""
Переприменить сумму PayPlat из quote_amount (last_webhook_payload или create_response).

Используйте если заявка Completed с неверной суммой: первый SUCCESS закрыл
сделку, повторный SUCCESS с корректировкой приняли с HTTP 200, но сумму не
пересчитали (баг early-return в payplat_views до фикса).

Проверка (только смотрит, APPLY не делает — скрипт всегда применяет через
handle_psp_success_webhook; при равных суммах outcome=idempotent):

  docker compose exec -T \\
    -e PAY_IN_ID=36ac9db1-b99c-4ca1-8e8e-1a810cbb59b4 app \\
    python manage.py shell < titanpay/basics/shell_payplat_reapply_success_amount.py

То же по shop_internal_id / provider order_id:

  docker compose exec -T \\
    -e SHOP_INTERNAL_ID=36ac9db1-b99c-4ca1-8e8e-1a810cbb59b4 app \\
    python manage.py shell < titanpay/basics/shell_payplat_reapply_success_amount.py

  docker compose exec -T -e PROVIDER_ORDER_ID=273166 app \\
    python manage.py shell < titanpay/basics/shell_payplat_reapply_success_amount.py

Только диагностика без пересчёта:

  docker compose exec -T \\
    -e PAY_IN_ID=36ac9db1-b99c-4ca1-8e8e-1a810cbb59b4 -e DRY_RUN=1 app \\
    python manage.py shell < titanpay/basics/shell_payplat_reapply_success_amount.py
"""
from __future__ import annotations

import os

from django.db import transaction

from payments.models import PayIn, PayplatPayInSession
from payments.payplat_client import payplat_webhook_paid_amount
from payments.psp_payin import handle_psp_success_webhook
from trade.models import InOrder

PAY_IN_ID = (os.environ.get("PAY_IN_ID") or "").strip()
SHOP_INTERNAL_ID = (os.environ.get("SHOP_INTERNAL_ID") or "").strip()
PROVIDER_ORDER_ID = (os.environ.get("PROVIDER_ORDER_ID") or "").strip()
DRY_RUN = (os.environ.get("DRY_RUN") or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_session() -> PayplatPayInSession | None:
    if PAY_IN_ID:
        pay_in = PayIn.objects.filter(pk=PAY_IN_ID).select_related("order").first()
        if pay_in is None:
            print(f"PayIn {PAY_IN_ID!r} not found")
            return None
        session = PayplatPayInSession.objects.filter(pay_in=pay_in).select_related("pay_in", "pay_in__order").first()
        if session is None:
            print("No PayPlat session for PAY_IN_ID")
        return session

    if SHOP_INTERNAL_ID:
        session = (
            PayplatPayInSession.objects.filter(external_id=SHOP_INTERNAL_ID)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session is None:
            pay_in = PayIn.objects.filter(pk=SHOP_INTERNAL_ID).first()
            if pay_in is not None:
                session = (
                    PayplatPayInSession.objects.filter(pay_in=pay_in)
                    .select_related("pay_in", "pay_in__order")
                    .first()
                )
        if session is None:
            print(f"No PayPlat session for SHOP_INTERNAL_ID={SHOP_INTERNAL_ID!r}")
        return session

    if PROVIDER_ORDER_ID:
        session = (
            PayplatPayInSession.objects.filter(provider_order_id=str(PROVIDER_ORDER_ID))
            .select_related("pay_in", "pay_in__order")
            .order_by("-id")
            .first()
        )
        if session is None:
            print(f"No PayPlat session for PROVIDER_ORDER_ID={PROVIDER_ORDER_ID!r}")
        return session

    print("ERROR: set PAY_IN_ID or SHOP_INTERNAL_ID or PROVIDER_ORDER_ID")
    return None


def run() -> None:
    session = _resolve_session()
    if session is None:
        return

    pay_in = session.pay_in
    if pay_in is None or pay_in.order_id is None:
        print("PayIn without InOrder")
        return

    body = session.last_webhook_payload or session.create_response or {}
    paid = payplat_webhook_paid_amount(body)
    invoice = body.get("invoice") if isinstance(body, dict) else None
    fiat = (invoice or {}).get("fiat_amount") if isinstance(invoice, dict) else None
    quote = (invoice or {}).get("quote_amount") if isinstance(invoice, dict) else None

    print(f"PayIn id: {pay_in.id}")
    print(f"external_id: {session.external_id}")
    print(f"provider_order_id: {session.provider_order_id}")
    print(f"PayIn amount now: {pay_in.amount}")
    print(f"InOrder status: {pay_in.order.status.name if pay_in.order and pay_in.order.status else '-'}")
    print(f"InOrder amount now: {pay_in.order.amount if pay_in.order else '-'}")
    print(f"last webhook status: {(body or {}).get('status')}")
    print(f"invoice.fiat_amount: {fiat}")
    print(f"invoice.quote_amount: {quote}")
    print(f"parsed paid (quote_amount): {paid}")
    print(f"recalculated flag: order={getattr(pay_in.order, 'recalculated', None)} pay_in={pay_in.recalculated}")

    if DRY_RUN:
        print("DRY_RUN=1 — пересчёт не применяем")
        if paid is not None and pay_in.order and paid != pay_in.order.amount:
            print(f"NEED_RECALC: {pay_in.order.amount} → {paid}")
        elif paid is not None and pay_in.order and paid == pay_in.order.amount:
            print("OK: сумма уже равна quote_amount")
        return

    with transaction.atomic():
        order = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
        outcome = handle_psp_success_webhook(order, body)
        order.refresh_from_db()
        pay_in.refresh_from_db()
    print(f"outcome: {outcome}")
    print(f"PayIn amount after: {pay_in.amount}")
    print(f"InOrder amount after: {order.amount} recalculated={order.recalculated}")


run()
