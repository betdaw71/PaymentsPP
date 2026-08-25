"""
Проверка GiPay API: методы, баланс, тестовый create payment.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_gipay_probe_api.py

  docker compose exec -T app env GIPAY_PROBE_AMOUNT=7000 GIPAY_PROBE_METHOD=kztg \\
    python manage.py shell < titanpay/basics/shell_gipay_probe_api.py
"""
from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal

from django.conf import settings

from payments.gipay_client import gipay_create_payment, gipay_get_balance, gipay_get_methods

CURRENCY = os.environ.get("GIPAY_PROBE_CURRENCY", "KZT").strip().upper()
AMOUNT = Decimal(os.environ.get("GIPAY_PROBE_AMOUNT", "7000"))
METHOD = os.environ.get("GIPAY_PROBE_METHOD", "").strip()


def _print(label: str, ok: bool, data) -> None:
    print(f"\n=== {label} ===")
    print("ok:", ok)
    print(json.dumps(data if isinstance(data, dict) else {"payload": data}, ensure_ascii=False, indent=2))


def run() -> None:
    print("GiPay API probe")
    print(f"  base:       {getattr(settings, 'GIPAY_API_BASE', '')}")
    print(f"  merchant:   {getattr(settings, 'GIPAY_MERCHANT_ID', '')}")
    print(f"  method env: {getattr(settings, 'GIPAY_PAYIN_METHOD', 'kztg')}")

    ok, methods = gipay_get_methods(currency=CURRENCY)
    _print(f"GET /api/v2/methods?currency={CURRENCY}", ok, methods)

    ok, balance = gipay_get_balance()
    _print("GET /api/v2/balance", ok, balance)

    method = METHOD or getattr(settings, "GIPAY_PAYIN_METHOD", "kztg")
    order_id = f"probe-{uuid.uuid4().hex[:12]}"
    print(f"\n=== POST /api/v2/payments (probe orderId={order_id}, method={method}) ===")

    ok, created = gipay_create_payment(
        amount=AMOUNT,
        order_id=order_id,
        currency=CURRENCY,
        payer_user_id=f"probe-user-{uuid.uuid4().hex[:8]}",
        method=method,
    )
    _print(f"create payment amount={AMOUNT} method={method}", ok, created)

    if ok and isinstance(created, dict):
        result = created.get("result") or {}
        print("\nRequisites preview:")
        print(f"  state:     {result.get('state')}")
        print(f"  address:   {result.get('address')}")
        print(f"  recipient: {result.get('recipient')}")
        print(f"  bank:      {result.get('bankName') or result.get('bank')}")
        print(f"  url:       {created.get('url')}")
    elif not ok:
        err = created.get("error", {}) if isinstance(created, dict) else created
        print("\nIf code 40003 — у GiPay не привязан method к мерчанту M_ELKSZ3Z9.")
        print("Попросите поддержку: включить method kztg для KZT и прислать точный method code из GET /methods.")


run()
