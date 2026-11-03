"""Диагностика одной заявки: статус, LayerOne session, webhook traces, gap по сумме.

  MERCHANT_ORDER_ID=23948169155 \\
    docker compose exec -T -e MERCHANT_ORDER_ID=23948169155 app \\
    python manage.py shell < titanpay/basics/shell_diagnose_order_recalc.py

Опционально EXPECTED_AMOUNT=10004.50
APPLY=1 — применить last_webhook / последний success-колбек через handle_psp_success_webhook
(ledger + колбек мерчанту), если сумма отличается.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.db import transaction

from payments.models import LayeronePayInSession, PayIn, PayInTraceLog
from payments.psp_payin import (
    handle_psp_success_webhook,
    parse_psp_webhook_paid_amount,
    psp_success_webhook_allows_completed_recalc,
)

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
ORDER_HINT = (os.environ.get("MERCHANT_ORDER_ID") or os.environ.get("ORDER") or "23948169155").strip()
EXPECTED_RAW = (os.environ.get("EXPECTED_AMOUNT") or "").strip()
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes", "on"}


def money(v):
    if v is None:
        return None
    return Decimal(str(v)).quantize(Q2, rounding=ROUND_HALF_UP)


def when(dt):
    return dt.astimezone(MSK).strftime("%Y-%m-%d %H:%M:%S %Z") if dt else "-"


def payload_dict(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def run() -> None:
    print("=" * 72)
    print(f"ORDER RECALC DIAGNOSE  hint={ORDER_HINT}  APPLY={int(APPLY)}")
    print("=" * 72)

    pay_in = (
        PayIn.objects.filter(merchant_order_id=ORDER_HINT)
        .select_related(
            "status",
            "merchant__user",
            "payment_system",
            "order__status",
            "order__payment_details__group__trader__user",
        )
        .order_by("-created_at")
        .first()
    )
    if pay_in is None:
        print("NOT FOUND by merchant_order_id")
        return

    order = pay_in.order
    trader = "-"
    if order and order.payment_details_id and order.payment_details.group_id:
        t = order.payment_details.group.trader
        trader = t.user.username if t and t.user_id else "-"

    print(f"pay_in:            {pay_in.id}")
    print(f"merchant_order_id: {pay_in.merchant_order_id}")
    print(f"merchant:          {pay_in.merchant.user.username if pay_in.merchant_id else '-'}")
    print(f"ps:                {getattr(pay_in.payment_system, 'name', None)}")
    print(f"payin_status:      {pay_in.status.name if pay_in.status else '-'}")
    print(f"payin_recalc:      {pay_in.recalculated}")
    print(f"trader:            {trader}")
    if order is None:
        print("NO InOrder")
        return
    print(f"order:             {order.id}")
    print(f"order_status:      {order.status.name if order.status else '-'}")
    print(f"amount:            {order.amount}")
    print(f"usd_amount:        {order.usd_amount}")
    print(f"recalculated:      {order.recalculated}")
    print(f"recalc_amount:     {order.recalculated_amount}")
    print(f"created:           {when(order.creation_date)}")
    print(f"completed:         {when(order.completion_date)}")

    expected = money(EXPECTED_RAW) if EXPECTED_RAW else None
    if expected is not None:
        cur = money(order.amount)
        print(f"expected:          {expected}  gap={money(expected - cur) if cur is not None else '-'}")

    sess = LayeronePayInSession.objects.filter(pay_in=pay_in).order_by("-updated_at").first()
    if sess is None:
        print("\nLayerOne session: НЕТ")
    else:
        print("\nLayerOne session:")
        print(f"  provider_order:  {getattr(sess, 'provider_order_id', None) or getattr(sess, 'layerone_order_id', None)}")
        print(f"  provider_payment:{getattr(sess, 'provider_payment_id', None) or getattr(sess, 'layerone_payment_id', None)}")
        print(f"  last_state:      {sess.last_notified_state}")
        print(f"  updated:         {when(sess.updated_at)}")
        last = payload_dict(sess.last_webhook_payload)
        paid = money(parse_psp_webhook_paid_amount(last)) if last else None
        allow = psp_success_webhook_allows_completed_recalc(last) if last else False
        print(f"  last_cb_amount:  {paid}  allow_completed_recalc={int(allow)}")
        if last:
            keys = ",".join(list(last.keys())[:16])
            print(f"  last_cb_keys:    {keys}")

    traces = PayInTraceLog.objects.filter(pay_in=pay_in).order_by("created_at")
    print(f"\nPayInTraceLog: n={traces.count()}")
    for t in traces:
        body = payload_dict(t.body)
        paid = money(parse_psp_webhook_paid_amount(body)) if body else None
        note = (t.note or "")[:120]
        print(
            f"  {when(t.created_at)}  {t.direction:22}  parsed_amount={paid}  note={note}"
        )
        if t.direction and t.direction.endswith("_webhook") and body:
            allow = psp_success_webhook_allows_completed_recalc(body)
            print(f"    allow_completed_recalc={int(allow)}  keys={','.join(list(body.keys())[:12])}")

    # Choose best body for reapply: last session webhook, else latest success webhook trace
    body = payload_dict(getattr(sess, "last_webhook_payload", None) if sess else None)
    if not body:
        for t in reversed(list(traces)):
            if t.direction == "layerone_webhook":
                body = payload_dict(t.body)
                if body:
                    break
    paid = money(parse_psp_webhook_paid_amount(body)) if body else None
    cur = money(order.amount)
    print("\nVERDICT:")
    if not body:
        print("  нет сохранённого LayerOne webhook body — провайдер либо не слал, либо мы не записали")
        return
    if paid is None:
        print("  webhook есть, сумму распарсить не смогли")
        return
    if paid == cur:
        print(f"  сумма уже {cur} (= last CB). Если Melbet ждёт другое — уточни EXPECTED_AMOUNT у мерчанта")
        return
    allow = psp_success_webhook_allows_completed_recalc(body)
    print(f"  GAP: current={cur}  last_cb={paid}  delta={money(paid - cur)}  allow={int(allow)}")
    print("  Причина исторически: LayerOne view early-return на Completed (колбек глотался).")
    if not APPLY:
        print("  DRY: APPLY=1 применит last CB через handle_psp_success_webhook (+ колбек мерчанту)")
        return
    if order.status.name != "Completed":
        print(f"  SKIP APPLY: статус {order.status.name}")
        return
    with transaction.atomic():
        locked = type(order).objects.select_for_update().get(pk=order.pk)
        kind = handle_psp_success_webhook(locked, body)
    order.refresh_from_db()
    pay_in.refresh_from_db()
    print(f"  APPLY result={kind}  amount_now={order.amount}  recalculated={order.recalculated}")


run()
