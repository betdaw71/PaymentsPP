"""HTTP client for ExpayOne PSP (H2H pay-in, cancel, webhook mapping)."""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def expayone_trader_username() -> str:
    return getattr(settings, "EXPAYONE_TRADER_USERNAME", "expayone1")


def is_expayone_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == expayone_trader_username()


def expayone_callback_url() -> str:
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/expayone/"


def _gateway_map() -> dict[str, str]:
    raw = getattr(settings, "EXPAYONE_GATEWAY_MAP", None)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("EXPAYONE_GATEWAY_MAP is not valid JSON")
    return {
        "Sber": "sberbank",
        "SBP": "sbp",
        "SberPay": "sberbank",
        "Tinkoff": "tinkoff",
        "C2C": "c2c",
        "C2CKZT": "c2c",
    }


def payment_system_to_gateway(payment_system_name: str) -> str | None:
    return _gateway_map().get(payment_system_name)


def payment_detail_type_for_ps(payment_system_name: str) -> str:
    from titanpay.settings import SBP_NAME, SBERPAY_NAME

    if payment_system_name in (SBP_NAME, SBERPAY_NAME):
        return "phone"
    return "card"


def _headers() -> dict[str, str]:
    token = (getattr(settings, "EXPAYONE_ACCESS_TOKEN", None) or "").strip()
    return {
        "Accept": "application/json",
        "Access-Token": token,
        "Content-Type": "application/json",
    }


def _api_base() -> str:
    return (getattr(settings, "EXPAYONE_API_BASE", "") or "").rstrip("/")


def _parse_envelope(r: requests.Response) -> tuple[bool, dict[str, Any] | str]:
    try:
        body = r.json() if r.content else {}
    except ValueError:
        body = {"raw": r.text[:2000]}
    if not isinstance(body, dict):
        return False, {"error": str(body)}
    if r.status_code >= 500:
        return False, body
    if r.status_code == 422:
        return False, body
    if r.status_code == 400 and body.get("success") is False:
        return False, body
    if not r.ok:
        return False, body
    if body.get("success") is False:
        return False, body
    data = body.get("data")
    if isinstance(data, dict):
        return True, data
    return True, body


def _request(method: str, path: str, *, json_payload: dict | None = None, timeout: int = 60) -> tuple[bool, dict[str, Any] | str]:
    token = (getattr(settings, "EXPAYONE_ACCESS_TOKEN", None) or "").strip()
    if not token:
        return False, "EXPAYONE_ACCESS_TOKEN is empty"
    base = _api_base()
    if not base:
        return False, "EXPAYONE_API_BASE is empty"
    url = f"{base}/{path.lstrip('/')}"
    try:
        r = requests.request(method, url, json=json_payload, headers=_headers(), timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("ExpayOne %s %s failed: %s", method, path, exc)
        return False, str(exc)
    return _parse_envelope(r)


def expayone_create_h2h_order(
    *,
    amount: Decimal,
    external_id: str,
    payment_detail_type: str,
    callback_url: str | None = None,
    payment_gateway: str | None = None,
    currency: str | None = None,
) -> tuple[bool, dict[str, Any] | str]:
    """payment_gateway и currency взаимоисключающие (документация ExpayOne)."""
    merchant_id = (getattr(settings, "EXPAYONE_MERCHANT_ID", None) or "").strip()
    if not merchant_id:
        return False, "EXPAYONE_MERCHANT_ID is empty"
    if payment_gateway and currency:
        return False, "use payment_gateway or currency, not both"
    if not payment_gateway and not currency:
        return False, "payment_gateway or currency required"

    payload = {
        "external_id": external_id,
        "amount": float(amount),
        "merchant_id": merchant_id,
        "payment_detail_type": payment_detail_type,
        "callback_url": callback_url or expayone_callback_url(),
    }
    if payment_gateway:
        payload["payment_gateway"] = payment_gateway
    else:
        payload["currency"] = currency.lower()
    return _request("POST", "/api/h2h/order", json_payload=payload)


def expayone_cancel_order(provider_order_id: str) -> tuple[bool, dict[str, Any] | str]:
    if not provider_order_id:
        return False, "empty order_id"
    return _request("PATCH", f"/api/h2h/order/{provider_order_id}/cancel")


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _norm_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (ignore pending)."""
    st = _norm_status(body.get("status"))
    sub = _norm_status(body.get("sub_status"))
    if st == "success":
        return "success"
    if sub in ("successfully_paid", "successfully_paid_by_resolved_dispute"):
        return "success"
    if st == "fail":
        return "fail"
    if sub in ("expired", "cancelled", "canceled_by_dispute"):
        return "fail"
    return None


def expayone_map_requisite(order_data: dict) -> dict:
    """AvaPay payment_details для ответа мерчанту."""
    pd = order_data.get("payment_detail") or {}
    if not isinstance(pd, dict):
        return {}
    detail = (pd.get("detail") or "").strip()
    if not detail:
        return {}
    detail_type = (pd.get("detail_type") or "").lower()
    initials = pd.get("initials") or order_data.get("payment_gateway_name") or ""
    bank = order_data.get("payment_gateway_name") or order_data.get("payment_gateway") or ""
    if detail_type == "phone":
        return {"phone": detail, "owner": initials, "bank": bank}
    if detail_type == "account_number":
        return {"deposit_number": detail, "owner": initials, "bank": bank}
    return {"card_number": detail, "owner": initials, "bank": bank}


def expayone_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import ExpayonePayInSession

    s = ExpayonePayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    cr = s.create_response or {}
    req = expayone_map_requisite(cr)
    from payments.psp_payin import requisite_payload_has_fields

    return req if requisite_payload_has_fields(req) else None


def expayone_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import ExpayonePayInSession

    try:
        s = ExpayonePayInSession.objects.get(pay_in=pay_in)
    except ExpayonePayInSession.DoesNotExist:
        return
    if not s.provider_order_id:
        return
    ok, _ = expayone_cancel_order(s.provider_order_id)
    if not ok:
        logger.warning(
            "ExpayOne cancel failed PayIn=%s provider_order_id=%s",
            pay_in.id,
            s.provider_order_id,
        )


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = expayone_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def try_attach_expayone_session(pay_in: Any) -> bool | None:
    """ExpayOne API для подобранной виртуальной группы expayone1 (любой PS группы)."""
    from payments.models import ExpayonePayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_expayone_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    ps_name = pay_in.payment_system.name if pay_in.payment_system else ""
    gateway = payment_system_to_gateway(ps_name)
    currency_sym = (pay_in.currency.symbol or "").strip().lower() if pay_in.currency else ""
    use_currency_only = getattr(settings, "EXPAYONE_USE_CURRENCY_FOR_C2C", True)
    if use_currency_only and currency_sym:
        gateway = None
    elif not gateway:
        logger.error("ExpayOne: no gateway mapping for payment_system=%s", ps_name)
        return False

    session, _ = ExpayonePayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": str(pay_in.id), "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = str(pay_in.id)
    session.save(update_fields=["external_id", "updated_at"])

    ok, data = expayone_create_h2h_order(
        amount=pay_in.amount,
        external_id=str(pay_in.id),
        payment_gateway=gateway,
        currency=currency_sym if gateway is None else None,
        payment_detail_type=payment_detail_type_for_ps(ps_name),
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("ExpayOne create order failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    session.provider_order_id = (session.create_response or {}).get("order_id") or ""
    session.save(update_fields=["create_response", "provider_order_id", "updated_at"])

    req = expayone_map_requisite(session.create_response)
    if not req.get("card_number") and not req.get("phone") and not req.get("deposit_number"):
        if session.provider_order_id:
            expayone_cancel_order(session.provider_order_id)
        session.provider_order_id = ""
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.save(update_fields=["create_response", "provider_order_id", "updated_at"])
        logger.error("ExpayOne: no requisite PayIn=%s", pay_in.id)
        return False
    return True
