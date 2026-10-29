"""Shared Aggrepay v2 webhook payload helpers (GiPay / LayerOne / Protocol).

Create/callback bodies are often wrapped:
  {"status": true, "result": {"id": "...", "orderId": "...", "state": "finished"}}
while PayPlat-style callbacks are flat. We flatten before matching session/status.
"""
from __future__ import annotations

_SUCCESS_STATES = frozenset({"finished", "paid", "success", "completed", "payed"})
_FAIL_STATES = frozenset({"canceled", "cancelled", "expired", "failed", "timeout", "error"})


def webhook_core(body: dict | None) -> dict:
    """Flatten result/data envelopes; top-level non-empty keys win."""
    if not isinstance(body, dict):
        return {}
    core: dict = {}
    for nested_key in ("data", "result"):
        nested = body.get(nested_key)
        if isinstance(nested, dict):
            core.update(nested)
    for key, value in body.items():
        if key in ("data", "result"):
            continue
        if value not in (None, ""):
            core[key] = value
    return core


def webhook_state(body: dict | None) -> str:
    core = webhook_core(body)
    raw = core.get("state")
    if isinstance(raw, bool) or raw in (None, ""):
        for key in ("paymentState", "payment_state"):
            alt = core.get(key)
            if alt not in (None, "", True, False):
                raw = alt
                break
        status = core.get("status")
        if isinstance(status, str) and status.strip():
            raw = raw or status
    if isinstance(raw, bool) or raw is None:
        return ""
    return str(raw).strip().lower().replace("-", "_")


def webhook_ids(body: dict | None) -> tuple[str, str]:
    """(merchant orderId, provider payment id)."""
    core = webhook_core(body)
    order_id = str(
        core.get("orderId")
        or core.get("order_id")
        or core.get("merchantOrderId")
        or core.get("merchant_order_id")
        or ""
    ).strip()
    payment_id = str(
        core.get("id") or core.get("paymentId") or core.get("payment_id") or ""
    ).strip()
    return order_id, payment_id


def webhook_outcome(body: dict | None) -> str | None:
    """success | fail | None (ignore intermediate, including status:true + state:created)."""
    state = webhook_state(body)
    if state in _SUCCESS_STATES:
        return "success"
    if state in _FAIL_STATES:
        return "fail"
    return None
