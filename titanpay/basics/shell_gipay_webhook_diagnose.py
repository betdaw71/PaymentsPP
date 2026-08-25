"""
Диагностика GiPay webhook: сессии, trace, подпись, последние логи.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_gipay_webhook_diagnose.py

С конкретным PayIn:
  docker compose exec -T -e PAYIN_ID=<uuid> app python manage.py shell < titanpay/basics/shell_gipay_webhook_diagnose.py
"""
from __future__ import annotations

import json
import os

from django.conf import settings

from payments.gipay_client import gipay_callback_url, verify_webhook_signature
try:
    from payments.gipay_client import webhook_signature_debug_hint
except ImportError:
    def webhook_signature_debug_hint(raw_body, signature):  # type: ignore[no-redef]
        return "update app image (git pull + rebuild)"
from payments.models import GipayPayInSession, PayIn, PayInTraceLog
from payments.payin_trace import Direction

PAYIN_ID = (os.environ.get("PAYIN_ID") or "").strip()
LIMIT = int(os.environ.get("LIMIT", "10"))


def _mask(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def print_env() -> None:
    print("=== GiPay env ===")
    print(f"  GIPAY_API_BASE:     {getattr(settings, 'GIPAY_API_BASE', '')}")
    print(f"  GIPAY_MERCHANT_ID:  {getattr(settings, 'GIPAY_MERCHANT_ID', '')}")
    print(f"  GIPAY_SECRET_KEY:   {_mask(getattr(settings, 'GIPAY_SECRET_KEY', ''))}")
    print(f"  GIPAY_API_KEY:      {_mask(getattr(settings, 'GIPAY_API_KEY', ''))}")
    print(f"  callbackUri:        {gipay_callback_url()}")
    print(f"  SKIP_VERIFY:        {getattr(settings, 'GIPAY_WEBHOOK_SKIP_VERIFY', False)}")


def print_sessions() -> None:
    print(f"\n=== Last {LIMIT} GipayPayInSession ===")
    qs = GipayPayInSession.objects.select_related("pay_in", "pay_in__order").order_by("-created_at")
    if PAYIN_ID:
        qs = qs.filter(pay_in_id=PAYIN_ID)
    rows = list(qs[:LIMIT])
    if not rows:
        print("  (none)")
        return
    for s in rows:
        pay_in = s.pay_in
        order = pay_in.order if pay_in else None
        print("---")
        print(f"  pay_in:              {s.pay_in_id}")
        print(f"  external_id:         {s.external_id}")
        print(f"  provider_payment_id: {s.provider_payment_id or '-'}")
        print(f"  last_notified_state: {s.last_notified_state or '-'}")
        print(f"  in_order:            {order.id if order else '-'}")
        print(f"  in_order_status:     {order.status.name if order and order.status else '-'}")
        print(f"  pay_in_status:       {pay_in.status.name if pay_in and pay_in.status else '-'}")
        cr = s.create_response or {}
        err = cr.get("error") if isinstance(cr, dict) else None
        if err:
            print(f"  create_error:        {json.dumps(err, ensure_ascii=False)[:300]}")


def print_trace() -> None:
    print("\n=== GiPay webhook trace ===")
    qs = PayInTrace.objects.filter(direction=Direction.GIPAY_WEBHOOK).order_by("-created_at")
    if PAYIN_ID:
        qs = qs.filter(pay_in_id=PAYIN_ID)
    rows = list(qs[:LIMIT])
    if not rows:
        print("  (no gipay_webhook rows — callback ещё не дошёл до обработчика)")
        return
    for row in rows:
        print("---")
        print(f"  at:      {row.created_at}")
        print(f"  pay_in:  {row.pay_in_id}")
        print(f"  note:    {row.note}")
        body = row.body if isinstance(row.body, dict) else {}
        print(f"  state:   {body.get('state')}")
        print(f"  orderId: {body.get('orderId')}")


def print_signature_check() -> None:
    if not PAYIN_ID:
        return
    session = GipayPayInSession.objects.filter(pay_in_id=PAYIN_ID).first()
    if session is None:
        print(f"\n=== Signature check ===\n  PayIn {PAYIN_ID}: no GipayPayInSession")
        return
    body = session.last_webhook_payload or {
        "orderId": str(session.external_id or PAYIN_ID),
        "id": session.provider_payment_id or "test-id",
        "state": "finished",
        "currency": "KZT",
        "amount": "7000",
    }
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    import hashlib
    import hmac

    secret = (getattr(settings, "GIPAY_SECRET_KEY", "") or "").strip()
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest() if secret else ""
    print("\n=== Signature check (local) ===")
    print(f"  body:      {raw.decode('utf-8')}")
    print(f"  signature: {sig[:12]}…")
    print(f"  verify:    {verify_webhook_signature(raw, sig)}")
    print(f"  hint:      {webhook_signature_debug_hint(raw, sig)}")


def print_next_steps() -> None:
    print("\n=== Что проверить на сервере ===")
    print("  1) Логи входящих webhook:")
    print("     docker compose logs app --tail=300 | grep -i 'GiPay webhook'")
    print("  2) Если invalid signature — сверить GIPAY_SECRET_KEY с ЛК GiPay")
    print("  3) Временно (только тест): GIPAY_WEBHOOK_SKIP_VERIFY=true + recreate app")
    print("  4) Попросить GiPay переотправить callback после фикса URL/подписи")
    print("  5) payin_trace по PayIn:")
    print("     docker compose exec -T app python manage.py payin_trace <PAYIN_UUID>")


print_env()
print_sessions()
print_trace()
print_signature_check()
print_next_steps()
