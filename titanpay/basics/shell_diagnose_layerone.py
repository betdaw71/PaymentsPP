"""
LayerOne: последние сессии + probe GET /methods.

  docker compose exec -T app python manage.py shell < titanpay/basics/shell_diagnose_layerone.py
"""
from __future__ import annotations

import json
from django.conf import settings
from payments.layerone_client import (
    layerone_callback_url,
    layerone_get_methods,
    layerone_map_requisite,
    layerone_payin_method_for,
)
from payments.models import LayeronePayInSession
from payments.psp_payin import requisite_payload_has_fields


def _clip(obj, n=1200):
    text = json.dumps(obj, ensure_ascii=False, default=str)
    return text if len(text) <= n else text[:n] + "…"


print("=== LayerOne config ===")
print("base", getattr(settings, "LAYERONE_API_BASE", ""))
print("merchantId set", bool((getattr(settings, "LAYERONE_MERCHANT_ID", "") or "").strip()))
print("apiKey set", bool((getattr(settings, "LAYERONE_API_KEY", "") or "").strip()))
print("secret set", bool((getattr(settings, "LAYERONE_SECRET_KEY", "") or "").strip()))
print("method", getattr(settings, "LAYERONE_PAYIN_METHOD", ""))
print("map", getattr(settings, "LAYERONE_PAYIN_METHOD_MAP", ""))
print("C2CKZT ->", layerone_payin_method_for("C2CKZT"))
print("C2C ->", layerone_payin_method_for("C2C"))
print("callbackUri", layerone_callback_url())
print("assetOrBank", getattr(settings, "LAYERONE_ASSET_OR_BANK", "") or "(empty)")

ok, methods = layerone_get_methods(currency="KZT")
print("\n=== GET /api/v2/methods?currency=KZT ok=%s ===" % ok)
print(_clip(methods, 2500))

print("\n=== last 15 LayeronePayInSession ===")
qs = LayeronePayInSession.objects.select_related("pay_in__status", "pay_in__payment_system").order_by("-updated_at")[:15]
for s in qs:
    pi = s.pay_in
    cr = s.create_response or {}
    mapped = layerone_map_requisite(cr)
    err = cr.get("error") if isinstance(cr, dict) else None
    print(
        f"PayIn={pi.id if pi else None} ps={pi.payment_system.name if pi and pi.payment_system else None} "
        f"status={pi.status.name if pi and pi.status else None} "
        f"provider_id={s.provider_payment_id!r} mapped={mapped} has_req={requisite_payload_has_fields(mapped)} "
        f"error={err}"
    )
    print("  create:", _clip(cr, 800))
    if s.last_webhook_payload:
        print("  webhook:", _clip(s.last_webhook_payload, 500), "state", s.last_notified_state)
