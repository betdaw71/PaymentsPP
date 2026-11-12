"""
Пинг PayPlat payout: доходит ли create, не RATE-UNAVAILABLE.

По умолчанию сумма 1000 KZT (скорее лимит, чем реальная выплата).
Боевая сумма: AMOUNT=20000 SEND=1

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_payplat_payout_ping.py

  docker compose exec -T -e AMOUNT=20000 -e SEND=1 \\
    app python manage.py shell < titanpay/basics/shell_payplat_payout_ping.py
"""
from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal

from payments.payplat_client import payplat_create_payout, payplat_payout_create_rejected
from payments.payoutkzt_rate import fetch_payoutkzt_xe_quote, get_payoutkzt_rate

AMOUNT = Decimal(os.environ.get("AMOUNT", "1000"))
CARD = "".join(c for c in os.environ.get("CARD", "4400430312355685") if c.isdigit())
NAME = (os.environ.get("NAME") or "NURSULTAN").strip()
SURNAME = (os.environ.get("SURNAME") or "SHAYAKHMETOV").strip()
SEND = os.environ.get("SEND", "1").strip().lower() in ("1", "true", "yes")
SID = f"ping-{uuid.uuid4()}"


def dump(obj, n=2000):
    text = json.dumps(obj, ensure_ascii=False, default=str) if not isinstance(obj, str) else obj
    return text if len(text) <= n else text[:n] + "…"


print("=== local live XE ===")
q = fetch_payoutkzt_xe_quote()
print(q)
print("stored", get_payoutkzt_rate(live=False))

print("\n=== PayPlat POST /payout ===")
print(f"  send={SEND} amount={AMOUNT} card=…{CARD[-4:] if len(CARD)>=4 else CARD} name={NAME} {SURNAME}")
print(f"  shop_internal_id={SID}")
if not SEND:
    print("SKIP (set SEND=1)")
else:
    ok, data = payplat_create_payout(
        amount=AMOUNT,
        shop_internal_id=SID,
        card_number=CARD,
        name=NAME,
        surname=SURNAME,
    )
    body = data if isinstance(data, dict) else {"error": str(data)}
    print(f"  http_ok={ok} rejected={payplat_payout_create_rejected(body)}")
    print(f"  response={dump(body)}")
    code = str(body.get("code") or "")
    err = str(body.get("error") or "")
    pid = body.get("payout_id") or body.get("id") or body.get("order_id")
    if "RATE-UNAVAILABLE" in code or "rate unavailable" in err.lower():
        print("  VERDICT: PayPlat still cannot read our live rate")
    elif pid:
        print(f"  VERDICT: reached PayPlat, provider id={pid}")
    elif ok and not payplat_payout_create_rejected(body):
        print("  VERDICT: reached PayPlat (accepted, no id in body)")
    else:
        print("  VERDICT: reached PayPlat (business reject, not rate-unavailable)")
