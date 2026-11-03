"""Полный dump webhook/session payload по merchant_order_id.

  MERCHANT_ORDER_ID=23948169155 docker compose exec -T \\
    -e MERCHANT_ORDER_ID=23948169155 app \\
    python manage.py shell < titanpay/basics/shell_dump_order_webhooks.py
"""
from __future__ import annotations

import json
import os
from zoneinfo import ZoneInfo

from payments.models import LayeronePayInSession, PayIn, PayInTraceLog

MSK = ZoneInfo("Europe/Moscow")
HINT = (os.environ.get("MERCHANT_ORDER_ID") or "23948169155").strip()
AMOUNT_keys = (
    "amount",
    "init_amount",
    "amount_commission_less",
    "paid_amount",
    "quote_amount",
    "sum",
    "fiat_amount",
    "received_amount",
)


def when(dt):
    return dt.astimezone(MSK).strftime("%Y-%m-%d %H:%M:%S %Z") if dt else "-"


def dump(label, body, ts=None):
    print("\n" + "-" * 72)
    print(f"{label}  {when(ts) if ts else ''}")
    if not isinstance(body, dict):
        print(repr(body)[:500])
        return
    for k in amount_keys:
        if k in body:
            print(f"  {k}={body.get(k)!r}")
        result = body.get("result") if isinstance(body.get("result"), dict) else {}
        if k in result:
            print(f"  result.{k}={result.get(k)!r}")
    print(json.dumps(body, ensure_ascii=False, indent=2, default=str)[:4000])


pay_in = PayIn.objects.filter(merchant_order_id=HINT).order_by("-created_at").first()
if pay_in is None:
    print("NOT FOUND", HINT)
else:
    print(f"pay_in={pay_in.id} order={getattr(pay_in.order, 'id', None)} amount={getattr(pay_in.order, 'amount', None)}")
    sess = LayeronePayInSession.objects.filter(pay_in=pay_in).first()
    if sess:
        dump("session.last_webhook_payload", sess.last_webhook_payload or {}, sess.updated_at)
        dump("session.create_response", sess.create_response or {}, sess.created_at)
    for t in PayInTraceLog.objects.filter(pay_in=pay_in).order_by("created_at"):
        body = t.body
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                pass
        dump(f"trace.{t.direction}", body if isinstance(body, dict) else {"raw": body}, t.created_at)
