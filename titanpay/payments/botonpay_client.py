"""HTTP client for BotonPay PSP (https://botonpay.org/api-docs, pay-in deals API)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def botonpay_trader_username() -> str:
    return getattr(settings, "BOTONPAY_TRADER_USERNAME", "botonpay1")


def is_botonpay_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == botonpay_trader_username()


def botonpay_callback_url() -> str:
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/botonpay/"


def _api_base() -> str:
    return (getattr(settings, "BOTONPAY_API_BASE", "https://botonpay.org/api/public/v1") or "").rstrip("/")


def _api_key() -> str:
    return (getattr(settings, "BOTONPAY_API_KEY", None) or "").strip()


def _webhook_secret() -> str:
    secret = (getattr(settings, "BOTONPAY_WEBHOOK_SECRET", None) or "").strip()
    if secret:
        return secret
    return _api_key()


def _headers(*, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_api_key()}",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _parse_response(r: requests.Response) -> tuple[bool, dict[str, Any] | str]:
    try:
        body = r.json() if r.content else {}
    except ValueError:
        body = {"raw": r.text[:2000]}
    if not isinstance(body, dict):
        return False, {"error": str(body)}
    if not r.ok:
        return False, body
    if body.get("success") is False:
        return False, body
    return True, body


def _request(
    method: str,
    path: str,
    *,
    json_payload: dict | None = None,
    idempotency_key: str | None = None,
    timeout: int = 60,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    base = _api_base()
    if not base:
        return False, "BOTONPAY_API_BASE is empty"
    if not _api_key():
        return False, "BOTONPAY_API_KEY is missing"

    url = f"{base}/{path.lstrip('/')}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.BOTONPAY_OUT_REQUEST,
        body=json_payload or {},
        http_method=method,
        url=url,
        note="BotonPay API",
    )
    try:
        r = requests.request(
            method,
            url,
            json=json_payload,
            headers=_headers(idempotency_key=idempotency_key),
            timeout=timeout,
        )
    except requests.RequestException as exc:
        logger.exception("BotonPay %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.BOTONPAY_OUT_RESPONSE,
            body={"error": str(exc)},
            http_method=method,
            url=url,
            status_code=None,
            note="request failed",
        )
        return False, str(exc)

    ok, body = _parse_response(r)
    trace_log(
        pay_in=pay_in,
        direction=Direction.BOTONPAY_OUT_RESPONSE,
        body=body if isinstance(body, dict) else {"payload": body},
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="BotonPay API",
    )
    return ok, body


def _deal_from_response(body: dict) -> dict:
    deal = body.get("deal")
    return deal if isinstance(deal, dict) else body


def botonpay_create_pay_in(
    *,
    amount: Decimal,
    merchant_order_id: str,
    currency: str = "KZT",
    callback_url: str | None = None,
    success_url: str | None = None,
    cancel_url: str | None = None,
    client_name: str | None = None,
    customer_id: str | None = None,
    idempotency_key: str | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    """POST /api/public/v1/deals"""
    amt = amount
    if amt == amt.to_integral_value():
        amount_field: int | float = int(amt)
    else:
        amount_field = float(amt.quantize(Decimal("0.01")))

    payload: dict[str, Any] = {
        "merchant_order_id": merchant_order_id,
        "fiat": (currency or "KZT").strip().upper(),
        "amount_fiat": amount_field,
        "callback_url": callback_url or botonpay_callback_url(),
    }
    if success_url:
        payload["success_url"] = success_url
    if cancel_url:
        payload["cancel_url"] = cancel_url
    if client_name:
        payload["client_name"] = client_name
    if customer_id:
        payload["customer_id"] = customer_id

    idem = idempotency_key or merchant_order_id or str(uuid.uuid4())
    return _request("POST", "/deals", json_payload=payload, idempotency_key=idem, pay_in=pay_in)


def botonpay_cancel_deal(deal_ref: str, *, pay_in=None) -> tuple[bool, dict[str, Any] | str]:
    if not deal_ref:
        return False, "empty deal id"
    return _request("POST", f"/deals/{deal_ref}/cancel", json_payload={}, pay_in=pay_in)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _norm_event(raw: str | None) -> str:
    return (raw or "").strip().lower()


def botonpay_webhook_outcome(body: dict, *, webhook_event: str | None = None) -> str | None:
    """success | fail | None (intermediate)."""
    event = _norm_event(webhook_event or body.get("event"))
    status = _norm_status(body.get("status"))

    if event == "deal.completed" or status == "completed":
        return "success"

    if event == "deal.appeal_resolved":
        appeal = body.get("appeal") if isinstance(body.get("appeal"), dict) else {}
        if status == "completed":
            return "success"
        if appeal.get("outcome") == "merchant" or appeal.get("status") == "resolved_client":
            return "success"
        return "fail"

    if event in ("deal.cancelled", "deal.expired", "deal.failed"):
        return "fail"
    if status in ("cancelled", "expired", "failed"):
        return "fail"

    return None


def verify_botonpay_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    if getattr(settings, "BOTONPAY_WEBHOOK_SKIP_VERIFY", False):
        logger.warning("BotonPay webhook: BOTONPAY_WEBHOOK_SKIP_VERIFY is enabled")
        return True

    secret = _webhook_secret()
    sig = (signature or "").strip().lower()
    if not secret or not sig:
        return False

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest().lower()
    return hmac.compare_digest(expected, sig)


def find_botonpay_session_for_webhook(body: dict):
    from payments.models import BotonpayPayInSession

    merchant_order_id = body.get("merchant_order_id")
    if merchant_order_id:
        session = (
            BotonpayPayInSession.objects.filter(external_id=str(merchant_order_id))
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session:
            return session

    for key in ("deal_uuid", "deal_id", "id"):
        raw = body.get(key)
        if raw is None or raw == "":
            continue
        session = (
            BotonpayPayInSession.objects.filter(provider_deal_uuid=str(raw))
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session:
            return session
    return None


def botonpay_map_requisite(deal: dict) -> dict:
    if not isinstance(deal, dict):
        return {}

    payment_url = (deal.get("payment_url") or deal.get("deal_url") or "").strip()
    details = deal.get("payment_details")
    if not isinstance(details, dict):
        details = {}

    bank = (details.get("bank") or "").strip()
    owner = (details.get("holder") or "").strip()

    card = (details.get("card") or "").replace(" ", "")
    if card:
        digits = "".join(c for c in card if c.isdigit())
        if len(digits) >= 13:
            return {"card_number": digits[:19], "owner": owner, "bank": bank}

    phone = (details.get("phone") or "").strip()
    if phone:
        if not phone.startswith("+"):
            phone = f"+{''.join(c for c in phone if c.isdigit())}"
        return {"phone": phone, "owner": owner, "bank": bank or "СБП"}

    account = (details.get("account") or "").replace(" ", "")
    if account:
        return {"card_number": account, "owner": owner, "bank": bank}

    iban = (details.get("iban") or "").replace(" ", "")
    if iban:
        return {"card_number": iban, "owner": owner, "bank": bank}

    if payment_url:
        return {"payment_form_url": payment_url, "owner": owner, "bank": bank}

    return {}


def botonpay_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import BotonpayPayInSession
    from payments.psp_payin import requisite_payload_has_fields

    s = BotonpayPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    cr = s.create_response or {}
    deal = _deal_from_response(cr if isinstance(cr, dict) else {})
    req = botonpay_map_requisite(deal)
    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = botonpay_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def botonpay_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import BotonpayPayInSession

    try:
        s = BotonpayPayInSession.objects.get(pay_in=pay_in)
    except BotonpayPayInSession.DoesNotExist:
        return
    deal_ref = s.provider_deal_uuid or s.external_id
    ok, data = botonpay_cancel_deal(deal_ref, pay_in=pay_in)
    if not ok:
        logger.warning("BotonPay cancel failed PayIn=%s detail=%s", pay_in.id, data)


def try_attach_botonpay_session(pay_in: Any) -> bool | None:
    from payments.models import BotonpayPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_botonpay_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    merchant_order_id = str(pay_in.id)
    currency = pay_in.currency.symbol if pay_in.currency else "KZT"
    ps_name = pay_in.payment_system.name if pay_in.payment_system else ""

    session, _ = BotonpayPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": merchant_order_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = merchant_order_id
    session.payment_system_name = ps_name
    session.save(update_fields=["external_id", "payment_system_name", "updated_at"])

    client_name = None
    customer_id = None
    if getattr(pay_in, "client_id", None) and getattr(pay_in, "client", None):
        customer_id = str(pay_in.client.client_id)
        client_name = (getattr(pay_in.client, "name", None) or "").strip() or None

    ok, data = botonpay_create_pay_in(
        amount=pay_in.amount,
        merchant_order_id=merchant_order_id,
        currency=currency,
        success_url=getattr(pay_in, "success_url", None) or None,
        cancel_url=getattr(pay_in, "failed_url", None) or None,
        client_name=client_name,
        customer_id=customer_id,
        idempotency_key=merchant_order_id,
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("BotonPay create deal failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    deal = _deal_from_response(session.create_response)
    deal_uuid = deal.get("deal_uuid") or deal.get("id")
    if deal_uuid:
        session.provider_deal_uuid = str(deal_uuid)
    session.save(update_fields=["create_response", "provider_deal_uuid", "updated_at"])

    req = botonpay_map_requisite(deal)
    if not req:
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.provider_deal_uuid = ""
        session.save(update_fields=["create_response", "provider_deal_uuid", "updated_at"])
        if deal_uuid:
            botonpay_cancel_deal(str(deal_uuid), pay_in=pay_in)
        logger.error("BotonPay: no requisite PayIn=%s ps=%s", pay_in.id, ps_name)
        return False
    return True
