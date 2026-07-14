"""HTTP client for FairPay PSP (create payin, cancel, optional status/submit)."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def fairpay_trader_username() -> str:
    return getattr(settings, "FAIRPAY_TRADER_USERNAME", "fairpay_agg")


def is_fairpay_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == fairpay_trader_username()


def fairpay_callback_url() -> str:
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/fairpay/"


def _fairpay_headers() -> dict[str, str]:
    token = (getattr(settings, "FAIRPAY_API_TOKEN", None) or "").strip()
    return {"Authorization": token, "Content-Type": "application/json"}


def _post_json(path: str, payload: dict[str, Any], timeout: int = 30) -> requests.Response:
    base = (getattr(settings, "FAIRPAY_API_BASE", "") or "").rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    return requests.post(url, json=payload, headers=_fairpay_headers(), timeout=timeout)


def fairpay_create_payin(*, amount: Decimal, external_id: str, callback_url: str | None = None) -> tuple[bool, dict[str, Any] | str]:
    token = (getattr(settings, "FAIRPAY_API_TOKEN", None) or "").strip()
    if not token:
        return False, "FAIRPAY_API_TOKEN is empty"
    cb = callback_url or fairpay_callback_url()
    payload = {
        "amount": float(amount),
        "method_id": getattr(settings, "FAIRPAY_METHOD_ID", "cascade_intent"),
        "integration": getattr(settings, "FAIRPAY_INTEGRATION", "deeplink"),
        "external_id": external_id,
        "callback_url": cb,
    }
    try:
        r = _post_json("order/create/payin", payload)
    except requests.RequestException as exc:
        logger.exception("FairPay create payin request failed: %s", exc)
        return False, str(exc)
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"raw": r.text[:2000]}
    if not r.ok:
        return False, data if isinstance(data, dict) else {"error": str(data)}
    return True, data if isinstance(data, dict) else {"data": data}


def fairpay_cancel_order(provider_order_id: int) -> tuple[bool, dict[str, Any] | str]:
    token = (getattr(settings, "FAIRPAY_API_TOKEN", None) or "").strip()
    if not token:
        return False, "FAIRPAY_API_TOKEN is empty"
    try:
        r = _post_json("order/cancel", {"id": int(provider_order_id)})
    except requests.RequestException as exc:
        logger.exception("FairPay cancel failed: %s", exc)
        return False, str(exc)
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"raw": r.text[:2000]}
    if not r.ok:
        return False, data if isinstance(data, dict) else {"error": str(data)}
    return True, data if isinstance(data, dict) else {"data": data}


def fairpay_submit_utr(provider_order_id: int, utr: str) -> tuple[bool, dict[str, Any] | str]:
    token = (getattr(settings, "FAIRPAY_API_TOKEN", None) or "").strip()
    if not token:
        return False, "FAIRPAY_API_TOKEN is empty"
    try:
        r = _post_json("order/submit", {"id": int(provider_order_id), "utr": str(utr)})
    except requests.RequestException as exc:
        return False, str(exc)
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"raw": r.text[:2000]}
    if not r.ok:
        return False, data if isinstance(data, dict) else {"error": str(data)}
    return True, data if isinstance(data, dict) else {"data": data}


def fairpay_get_status(provider_order_id: int) -> tuple[bool, dict[str, Any] | str]:
    token = (getattr(settings, "FAIRPAY_API_TOKEN", None) or "").strip()
    if not token:
        return False, "FAIRPAY_API_TOKEN is empty"
    base = (getattr(settings, "FAIRPAY_API_BASE", "") or "").rstrip("/")
    url = f"{base}/order/status?{urlencode({'id': int(provider_order_id)})}"
    try:
        r = requests.get(url, headers=_fairpay_headers(), timeout=30)
    except requests.RequestException as exc:
        return False, str(exc)
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"raw": r.text[:2000]}
    if not r.ok:
        return False, data if isinstance(data, dict) else {"error": str(data)}
    return True, data if isinstance(data, dict) else {"data": data}


def fairpay_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import FairpayPayInSession

    try:
        s = pay_in.fairpay_session
    except FairpayPayInSession.DoesNotExist:
        return None
    cr = s.create_response or {}
    req = cr.get("requisite")
    if isinstance(req, dict) and req:
        return req
    return None


def fairpay_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import FairpayPayInSession

    try:
        s = FairpayPayInSession.objects.get(pay_in=pay_in)
    except FairpayPayInSession.DoesNotExist:
        return
    if s.provider_order_id is None:
        return
    ok, _ = fairpay_cancel_order(s.provider_order_id)
    if not ok:
        logger.warning("FairPay cancel API failed for PayIn %s provider_id=%s", pay_in.id, s.provider_order_id)


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = fairpay_requisite_for_payin(pay_in)
    if req is not None:
        representation["payment_details"] = req
    return representation


def try_attach_fairpay_session(pay_in: Any) -> bool | None:
    """FairPay API для подобранной виртуальной группы fairpay (любой PS группы)."""
    from payments.models import FairpayPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_fairpay_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    session, _ = FairpayPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": str(pay_in.id), "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = str(pay_in.id)
    session.save(update_fields=["external_id", "updated_at"])
    ok, data = fairpay_create_payin(amount=pay_in.amount, external_id=str(pay_in.id))
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("FairPay create payin failed for PayIn %s: %s", pay_in.id, data)
        return False
    session.create_response = data if isinstance(data, dict) else {"payload": data}
    pid = (session.create_response or {}).get("id")
    if pid is not None:
        try:
            session.provider_order_id = int(pid)
        except (TypeError, ValueError):
            session.provider_order_id = None
    session.save(update_fields=["create_response", "provider_order_id", "updated_at"])

    req = (session.create_response or {}).get("requisite")
    if not isinstance(req, dict) or not req:
        if session.provider_order_id is not None:
            fairpay_cancel_order(session.provider_order_id)
        session.provider_order_id = None
        session.create_response = {
            "error": "no_requisite_in_response",
            "upstream": session.create_response,
        }
        session.save(update_fields=["create_response", "provider_order_id", "updated_at"])
        logger.error("FairPay create payin OK but no requisite for PayIn %s", pay_in.id)
        return False
    return True
