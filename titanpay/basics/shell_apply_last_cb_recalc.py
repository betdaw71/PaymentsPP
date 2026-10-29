"""
Применить перерасчёт с last_webhook по 8 GiPay-заявкам, где колбек с новой суммой уже есть.

По умолчанию DRY_RUN. APPLY=1 — handle_psp_success_webhook (ledger + колбек мерчанту).

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_apply_last_cb_recalc.py

  docker compose exec -T -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_apply_last_cb_recalc.py
"""
from __future__ import annotations

import json
import os
import traceback
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from payments.models import GipayPayInSession, PayIn
from payments.psp_payin import handle_psp_success_webhook, parse_psp_webhook_paid_amount
from trade.models import InOrder

Q2 = Decimal("0.01")

# last CB amount differs from current — apply that CB, not the merchant's expected 1-tiyn figure
APPLY_UUIDS = [
    "4f687e57-886c-4c78-a798-d1b5581abaab",  # 23829018219  5000 -> 5001.49
    "3d181124-e17f-4549-9664-7ed6a83a8ac2",  # 23867114531  6799 -> 6800.76
    "d5b7c9f8-d027-4630-abb7-d1c18e6859dd",  # 23866293285  5000 -> 5001.49
    "3a27b78e-f7e4-4340-a066-7de850ec6e0b",  # 23866395303  5000 -> 5001.49
    "737c28e2-daf1-49ea-8fe1-3b63c3772b8b",  # 23866234767  5000 -> 5001.49
    "2b14b486-e6ed-436f-b321-e52a471116ef",  # 23867398013  29000 -> 29000.05
    "0ea5a41d-6687-4ea5-8620-205714616cec",  # 23867073917  5000 -> 5001.49
    "0fcc97d8-8f2e-41e9-83f3-7012aa9049b9",  # 23866416213  5000 -> 5001.49
]


def money(v):
    if v is None:
        return None
    return Decimal(str(v)).quantize(Q2, rounding=ROUND_HALF_UP)


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


def env_apply() -> bool:
    raw = (os.environ.get("APPLY") or "").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def run():
    apply = env_apply()
    print(f"last-CB recalc  mode={'APPLY' if apply else 'DRY_RUN'}\n")
    ok = fail = skip = 0
    for uid in APPLY_UUIDS:
        pay_in = PayIn.objects.filter(id=uid).select_related(
            "order", "order__status", "merchant__user"
        ).first()
        if pay_in is None:
            print(f"NOT FOUND {uid}")
            fail += 1
            continue
        order = pay_in.order
        moid = pay_in.merchant_order_id
        merch = pay_in.merchant.user.username if pay_in.merchant_id else "-"
        sess = GipayPayInSession.objects.filter(pay_in=pay_in).order_by("-updated_at").first()
        body = payload_dict(getattr(sess, "last_webhook_payload", None) if sess else None)
        paid = money(parse_psp_webhook_paid_amount(body)) if body else None
        cur = money(order.amount) if order else None
        print(
            f"{moid}  {uid}  merchant={merch}  status={order.status.name if order and order.status else '-'}  "
            f"current={cur}  last_cb={paid}"
        )
        if order is None or not body or paid is None:
            print("  SKIP: нет last_webhook / суммы")
            skip += 1
            continue
        if order.status.name != "Completed":
            print(f"  SKIP: статус {order.status.name}")
            skip += 1
            continue
        if paid == cur:
            print("  SKIP: сумма уже совпадает с last CB")
            skip += 1
            continue
        if not apply:
            print(f"  DRY: {cur} -> {paid}  (APPLY=1 применит + колбек мерчанту)")
            continue
        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=order.pk)
                outcome = handle_psp_success_webhook(locked, body)
            locked.refresh_from_db()
            print(f"  APPLY outcome={outcome}  now={money(locked.amount)}  recalc={locked.recalculated}")
            if outcome == "recalculated":
                ok += 1
            else:
                skip += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"  FAIL: {exc}")
            traceback.print_exc()
    print(f"\ndone apply_ok={ok} skip={skip} fail={fail}")
    if not apply:
        print("DRY_RUN — для применения: -e APPLY=1")


run()
