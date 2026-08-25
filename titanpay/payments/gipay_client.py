"""HTTP client for GiPay PSP (gipay.org, Aggrepay API v2)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def gipay_trader_username() -> str:
    return getattr(settings, "GIPAY_TRADER_USERNAME", "gipay1")


def is_gipay_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == gipay_trader_username()


def gipay_callback_url() -> str:
    explicit = (getattr(settings, "GIPAY_CALLBACK_URL", None) or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/gipay/"


def _api_key() -> str:
    return (getattr(settings, "GIPAY_API_KEY", None) or "").strip()


def _merchant_id() -> str:
    return (getattr(settings, "GIPAY_MERCHANT_ID", None) or "").strip()


def _secret_key() -> str:
    return (getattr(settings, "GIPAY_SECRET_KEY", None) or "").strip()


def _api_base() -> str:
    return (getattr(settings, "GIPAY_API_BASE", "https://gipay.org") or "").rstrip("/")


def _canonical_body(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _sign_body(body: str) -> str:
    return hmac.new(_secret_key().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def _headers(body: str) -> dict[str, str]:
    api_key = _api_key()
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Signature": _sign_body(body),
    }


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    if getattr(settings, "GIPAY_WEBHOOK_SKIP_VERIFY", False):
        logger.warning("GiPay webhook: GIPAY_WEBHOOK_SKIP_VERIFY is enabled")
        return True
    secret = _secret_key()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.strip(), expected)


def _request(
    method: str,
    path: str,
    *,
    json_payload: dict | None = None,
    timeout: int = 60,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    if not _api_key():
        return False, "GIPAY_API_KEY is empty"
    if not _merchant_id():
        return False, "GIPAY_MERCHANT_ID is empty"
    if not _secret_key():
        return False, "GIPAY_SECRET_KEY is empty"
    base = _api_base()
    if not base:
        return False, "GIPAY_API_BASE is empty"
    payload = json_payload or {}
    body = _canonical_body(payload)
    url = f"{base}/{path.lstrip('/')}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.GIPAY_OUT_REQUEST,
        body=payload,
        http_method=method,
        url=url,
        note="GiPay API",
    )
    try:
        if method.upper() == "GET":
            r = requests.request(method, url, headers=_headers(body), timeout=timeout)
        else:
            r = requests.request(method, url, data=body.encode("utf-8"), headers=_headers(body), timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("GiPay %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.GIPAY_OUT_RESPONSE,
            body={"error": str(exc)},
            http_method=method,
            url=url,
            status_code=None,
            note="request failed",
        )
        return False, str(exc)
    try:
        resp_body = r.json() if r.content else {}
    except ValueError:
        resp_body = {"raw": r.text[:2000]}
    trace_log(
        pay_in=pay_in,
        direction=Direction.GIPAY_OUT_RESPONSE,
        body=resp_body,
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="GiPay API",
    )
    if not isinstance(resp_body, dict):
        return False, {"error": str(resp_body)}
    if not r.ok or resp_body.get("status") is False:
        return False, resp_body
    return True, resp_body


def gipay_create_payment(
    *,
    amount: Decimal,
    order_id: str,
    currency: str,
    callback_url: str | None = None,
    payer_user_id: str | None = None,
    payer_ip: str | None = None,
    method: str | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    payin_method = (method or getattr(settings, "GIPAY_PAYIN_METHOD", None) or "kztg").strip()
    payload: dict[str, Any] = {
        "orderId": order_id,
        "merchantId": _merchant_id(),
        "amount": str(int(amount)) if amount == amount.to_integral_value() else str(amount),
        "currency": currency.upper(),
        "method": payin_method,
        "callbackUri": callback_url or gipay_callback_url(),
        "payer": {
            "userId": payer_user_id or order_id,
            "userIp": payer_ip or getattr(settings, "GIPAY_DEFAULT_PAYER_IP", "127.0.0.1"),
        },
    }
    asset_or_bank = (getattr(settings, "GIPAY_ASSET_OR_BANK", None) or "").strip()
    if asset_or_bank:
        payload["assetOrBank"] = asset_or_bank
    return _request("POST", "/api/v2/payments", json_payload=payload, pay_in=pay_in)


def gipay_get_methods(*, currency: str = "KZT") -> tuple[bool, dict[str, Any] | str]:
    """GET /api/v2/methods?currency=KZT — какие method codes доступны мерчанту."""
    cur = (currency or "KZT").strip().upper()
    return _request("GET", f"/api/v2/methods?currency={cur}", json_payload={}, pay_in=None)


def gipay_get_balance() -> tuple[bool, dict[str, Any] | str]:
    return _request("GET", "/api/v2/balance", json_payload={}, pay_in=None)


def _norm_state(raw: str | None) -> str:
    return (raw or "").strip().lower()


def gipay_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (ignore intermediate)."""
    state = _norm_state(body.get("state"))
    if state == "finished":
        return "success"
    if state in ("canceled", "cancelled", "expired", "failed"):
        return "fail"
    return None


def gipay_map_requisite(create_body: dict) -> dict:
    """Маппинг result из POST /api/v2/payments в payment_details для мерчанта."""
    result = create_body.get("result") if isinstance(create_body, dict) else {}
    if not isinstance(result, dict):
        result = create_body if isinstance(create_body, dict) else {}
    address = (result.get("address") or "").strip()
    owner = result.get("recipient") or ""
    bank = result.get("bankName") or result.get("bank") or ""
    if not address:
        url = (create_body.get("url") or "").strip() if isinstance(create_body, dict) else ""
        if url:
            return {"payment_form_url": url, "owner": owner, "bank": bank}
        return {}
    digits = "".join(c for c in address if c.isdigit())
    if len(digits) >= 16:
        return {"card_number": digits[:16], "owner": owner, "bank": bank}
    if address.startswith("+") or (digits and len(digits) <= 12):
        return {"phone": address if address.startswith("+") else f"+{digits}", "owner": owner, "bank": bank}
    return {"card_number": address, "owner": owner, "bank": bank}


def gipay_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import GipayPayInSession

    s = GipayPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    cr = s.create_response or {}
    req = gipay_map_requisite(cr)
    from payments.psp_payin import requisite_payload_has_fields

    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = gipay_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def try_attach_gipay_session(pay_in: Any) -> bool | None:
    """GiPay API для виртуальной группы gipay1."""
    from payments.models import GipayPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_gipay_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    currency_sym = (pay_in.currency.symbol or "KZT").strip().upper() if pay_in.currency else "KZT"
    external_id = str(pay_in.id)

    session, _ = GipayPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": external_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = external_id
    session.save(update_fields=["external_id", "updated_at"])

    payer_user_id = str(pay_in.id)
    if getattr(settings, "GIPAY_PAYER_USER_ID_FROM_CLIENT", False):
        if pay_in.client_id and getattr(pay_in, "client", None):
            payer_user_id = str(pay_in.client.client_id)

    ok, data = gipay_create_payment(
        amount=pay_in.amount,
        order_id=external_id,
        currency=currency_sym,
        payer_user_id=payer_user_id,
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("GiPay create payment failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    result = (session.create_response or {}).get("result") or {}
    session.provider_payment_id = str(result.get("id") or "")
    session.save(update_fields=["create_response", "provider_payment_id", "updated_at"])

    req = gipay_map_requisite(session.create_response)
    state = _norm_state(result.get("state"))
    if not req and state not in ("created",):
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.provider_payment_id = ""
        session.save(update_fields=["create_response", "provider_payment_id", "updated_at"])
        logger.error("GiPay: no requisite PayIn=%s state=%s", pay_in.id, state)
        return False
    return True if req else False


def gipay_cancel_if_linked(pay_in: Any) -> None:
    """GiPay v2 не документирует явный cancel pay-in — no-op с логом."""
    from payments.models import GipayPayInSession

    try:
        s = GipayPayInSession.objects.get(pay_in=pay_in)
    except GipayPayInSession.DoesNotExist:
        return
    if s.provider_payment_id:
        logger.info(
            "GiPay cancel skipped PayIn=%s provider_payment_id=%s (no API in Postman)",
            pay_in.id,
            s.provider_payment_id,
        )
