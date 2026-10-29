"""
Сырые колбеки PatriotPay по 4 заявкам с повторным paid.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_dump_patriot_dup_paid.py
"""
from __future__ import annotations

import json
from decimal import Decimal
from zoneinfo import ZoneInfo

from payments.models import PayIn, PayInTraceLog
from payments.patriotpay_client import patriotpay_webhook_paid_amount
from payments.psp_payin import parse_psp_webhook_paid_amount

MSK = ZoneInfo("Europe/Moscow")
IDS = [
    "ef43103a-08c0-40b1-a3f6-de4339200993",
    "8c04f95d-1625-4912-9cfc-4aaa9ba81652",
    "b9d4f455-bb64-4261-b6d4-2a71d9e4cdb1",
    "e5b35d34-6e93-4674-9a42-4fc4da2e9530",
]

AMOUNT_KEYS = (
    "amount",
    "paidAmount",
    "paid_amount",
    "factAmount",
    "fact_amount",
    "receivedAmount",
    "quote_amount",
    "fiat_amount",
    "crypto_amount",
)


def when(dt):
    if not dt:
        return "-"
    return dt.astimezone(MSK).strftime("%Y-%m-%d %H:%M:%S")


def payload(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def pick_amounts(obj, prefix=""):
    found = []
    if not isinstance(obj, dict):
        return found
    for k, v in obj.items():
        path = f"{prefix}.{k}" if prefix else k
        if k in AMOUNT_KEYS or k in {"sum", "receivedSumFromTaker", "receivedSumFromMaker"}:
            found.append((path, v))
        if isinstance(v, dict):
            found.extend(pick_amounts(v, path))
        elif isinstance(v, list):
            for i, item in enumerate(v[:3]):
                if isinstance(item, dict):
                    found.extend(pick_amounts(item, f"{path}[{i}]"))
    return found


print("PatriotPay duplicate-paid dump  (read-only)\n")
print("Парсер берёт по порядку: paidAmount/factAmount/receivedAmount, потом sum.amount, потом amount.")
print("invoice.amount в этих IPN обычно None — сумма в invoice.sum.amount.\n")

for uid in IDS:
    pay_in = PayIn.objects.filter(id=uid).select_related(
        "status", "order", "order__status", "merchant__user"
    ).first()
    print("=" * 96)
    if pay_in is None:
        print(f"NOT FOUND {uid}")
        continue
    order = pay_in.order
    print(
        f"pay_in={pay_in.id}  moid={pay_in.merchant_order_id}  "
        f"merchant={pay_in.merchant.user.username if pay_in.merchant_id else '-'}  "
        f"payin={pay_in.status.name if pay_in.status else '-'}  "
        f"order={order.status.name if order and order.status else '-'}  "
        f"amount={order.amount if order else '-'}"
    )
    traces = PayInTraceLog.objects.filter(
        pay_in=pay_in, direction="patriotpay_webhook"
    ).order_by("created_at")
    print(f"  traces={traces.count()}")
    for t in traces:
        body = payload(t.body)
        inv = body.get("invoice") if isinstance(body.get("invoice"), dict) else {}
        parsed_pp = patriotpay_webhook_paid_amount(body)
        parsed_shared = parse_psp_webhook_paid_amount(body)
        print(f"\n  {when(t.created_at)}  note={t.note}")
        print(f"    parser patriotpay={parsed_pp}  shared={parsed_shared}")
        print("    amount-поля в теле:")
        for path, val in pick_amounts(body):
            print(f"      {path} = {val!r}")
        print("    RAW JSON:")
        print(json.dumps(body, ensure_ascii=False, indent=2, default=str))
    print()
