"""HTTP client for Prochub PSP (https://prochub.pro, POST /api/invoice-in)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def prochub_trader_username() -> str:
    return getattr(settings, "PROCHUB_TRADER_USERNAME", "prochub1")


def is_prochub_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == prochub_trader_username()


def _parse_json_map(setting_name: str) -> dict[str, str]:
    raw = getattr(settings, setting_name, None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    try:
        data = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("%s is not valid JSON", setting_name)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def prochub_invoice_type_for(payment_system_name: str | None) -> str:
    ps = (payment_system_name or "").strip()
    mapped = _parse_json_map("PROCHUB_INVOICE_TYPE_MAP")
    if ps and ps in mapped and mapped[ps].strip():
        return mapped[ps].strip().upper()
    default = (getattr(settings, "PROCHUB_INVOICE_TYPE", None) or "").strip()
    if default:
        return default.upper()
    if ps in ("PHONEKZT", "PHONEKGS"):
        return "MOBILE_COM"
    if ps in ("QRKGS",):
        return "SBP"
    return "CARD"


def prochub_callback_url() -> str:
    explicit = (getattr(settings, "PROCHUB_CALLBACK_URL", None) or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/prochub/"


def _api_key() -> str:
    return (getattr(settings, "PROCHUB_API_KEY", None) or "").strip()


def _secret_key() -> str:
    return (getattr(settings, "PROCHUB_SECRET_KEY", None) or "").strip()


def _merchant_id() -> str:
    return (getattr(settings, "PROCHUB_MERCHANT_ID", None) or "").strip()


def _api_base() -> str:
    return (getattr(settings, "PROCHUB_API_BASE", "https://prochub.pro") or "").rstrip("/")


def _canonical_body(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _amount_int(amount: Decimal) -> int:
    d = Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(d)


def _sign_request(*, method: str, url: str, body: str = "") -> str:
    string_to_sign = f"{method.upper()}{url}{body}"
    digest = hmac.new(_secret_key().encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _headers(*, method: str, url: str, body: str = "") -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-api-key": _api_key(),
        "x-signature": _sign_request(method=method, url=url, body=body),
    }


def verify_webhook_token(received_token: str | None, expected_token: str | None) -> bool:
    if getattr(settings, "PROCHUB_WEBHOOK_SKIP_VERIFY", False):
        logger.warning("Prochub webhook: PROCHUB_WEBHOOK_SKIP_VERIFY is enabled")
        return True
    recv = (received_token or "").strip()
    exp = (expected_token or "").strip()
    if not recv or not exp:
        return False
    return hmac.compare_digest(recv, exp)


def _unwrap_invoice_response(resp_body: Any) -> dict[str, Any] | None:
    if not isinstance(resp_body, dict):
        return None
    inner = resp_body.get("data")
    if isinstance(inner, dict) and (
        inner.get("invoiceId") or inner.get("cardNumber") or inner.get("phoneNumber") or inner.get("walletNumber")
    ):
        return inner
    if resp_body.get("invoiceId"):
        return resp_body
    return None


def _request(
    method: str,
    path: str,
    *,
    json_payload: dict | None = None,
    send_json_body: bool = True,
    timeout: int = 60,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    if not _api_key():
        return False, "PROCHUB_API_KEY is empty"
    if not _secret_key():
        return False, "PROCHUB_SECRET_KEY is empty"
    base = _api_base()
    if not base:
        return False, "PROCHUB_API_BASE is empty"

    payload = json_payload or {}
    body = _canonical_body(payload) if method.upper() != "GET" and send_json_body and payload else ""
    url = f"{base}/{path.lstrip('/')}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.PROCHUB_OUT_REQUEST,
        body=payload if payload else {"_method": method, "_path": path},
        http_method=method,
        url=url,
        note="Prochub API",
    )
    try:
        headers = _headers(method=method, url=url, body=body)
        if method.upper() == "GET" or not body:
            r = requests.request(method, url, headers=headers, timeout=timeout)
        else:
            r = requests.request(method, url, data=body.encode("utf-8"), headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("Prochub %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.PROCHUB_OUT_RESPONSE,
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
        direction=Direction.PROCHUB_OUT_RESPONSE,
        body=resp_body,
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="Prochub API",
    )
    if not r.ok:
        return False, resp_body if isinstance(resp_body, dict) else {"error": str(resp_body)}
    if isinstance(resp_body, dict) and resp_body.get("error") is True:
        return False, resp_body
    invoice = _unwrap_invoice_response(resp_body)
    if invoice is None:
        if isinstance(resp_body, dict) and str(resp_body.get("status") or "").lower() == "success":
            return True, resp_body.get("data") if isinstance(resp_body.get("data"), dict) else resp_body
        return False, {"error": "unexpected_response_shape", "upstream": resp_body}
    return True, invoice


def prochub_create_invoice(
    *,
    amount: Decimal,
    internal_id: str,
    callback_url: str,
    callback_key: str,
    invoice_type: str,
    bank_code: str | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    merchant_id = _merchant_id()
    if not merchant_id:
        return False, "PROCHUB_MERCHANT_ID is empty"
    payload: dict[str, Any] = {
        "amount": _amount_int(amount),
        "internalRequestId": internal_id,
        "callbackUrl": callback_url,
        "callbackKey": callback_key,
        "merchantId": merchant_id,
        "type": invoice_type,
        "activeTime": int(getattr(settings, "PROCHUB_INVOICE_LIFETIME_MINUTES", 15) or 15),
    }
    if bank_code:
        payload["bankCode"] = bank_code
    return _request("POST", "/api/invoice-in", json_payload=payload, pay_in=pay_in)


def prochub_cancel_invoice(*, invoice_id: str, pay_in=None) -> tuple[bool, dict[str, Any] | str]:
    invoice_id = (invoice_id or "").strip()
    if not invoice_id:
        return False, "invoice_id is empty"
    return _request(
        "PATCH",
        f"/api/invoice-in/{invoice_id}/cancel",
        json_payload=None,
        send_json_body=False,
        pay_in=pay_in,
    )


def _norm_status(raw: str | None) -> str:
    if not isinstance(raw, str):
        return ""
    return raw.strip().upper().replace("-", "_")


def resolve_prochub_webhook_session(*, internal_id: str | None, invoice_id: str | None):
    from payments.models import PayIn, ProchubPayInSession

    iid = (internal_id or "").strip()
    inv_id = (invoice_id or "").strip()
    if iid:
        session = (
            ProchubPayInSession.objects.filter(external_id=iid)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session is not None:
            return session
    if inv_id:
        session = (
            ProchubPayInSession.objects.filter(provider_invoice_id=inv_id)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session is not None:
            return session
    if not iid:
        return None
    pay_in = PayIn.objects.filter(pk=iid).select_related("order__payment_details__group__trader").first()
    if pay_in is None or pay_in.order is None or pay_in.order.payment_details is None:
        return None
    if not is_prochub_trader(pay_in.order.payment_details.group.trader):
        return None
    token = secrets.token_urlsafe(24)
    session, _ = ProchubPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={
            "external_id": str(pay_in.id),
            "notification_token": token,
            "create_response": {},
            "last_webhook_payload": {},
        },
    )
    return session


def prochub_webhook_outcome(body: dict) -> str | None:
    status = _norm_status(body.get("status"))
    if status in ("SUCCESS", "SUCCESS_APPEAL", "SUCCESS_HAND", "SUCCESS_AUTO"):
        return "success"
    if status in ("CANCELED", "CANCELLED", "CANCELED_APPEAL"):
        return "fail"
    return None


def prochub_is_webhook_body(body: dict | None) -> bool:
    if not isinstance(body, dict):
        return False
    if str(body.get("type") or "").strip().lower() == "in" and body.get("invoiceId"):
        return True
    return bool(body.get("invoiceId") and body.get("status") and not body.get("internalId"))


def prochub_webhook_paid_amount(body: dict | None) -> Decimal | None:
    if not prochub_is_webhook_body(body):
        return None
    assert isinstance(body, dict)
    for key in ("newAmount", "new_amount", "amount"):
        raw = body.get(key)
        if raw is None:
            continue
        try:
            val = Decimal(str(raw).strip().replace(",", "."))
        except (ValueError, TypeError, ArithmeticError):
            continue
        if val > 0:
            return val
    return None


def prochub_success_webhook_allows_completed_recalc(body: dict | None) -> bool:
    if not isinstance(body, dict):
        return False
    return prochub_is_webhook_body(body) and prochub_webhook_outcome(body) == "success"


def prochub_map_requisite(create_body: dict) -> dict:
    body = create_body if isinstance(create_body, dict) else {}
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    card = str(data.get("cardNumber") or "").strip()
    phone = str(data.get("phoneNumber") or "").strip()
    wallet = str(data.get("walletNumber") or "").strip()
    owner = str(data.get("cardName") or data.get("holder") or "").strip()
    bank = str(data.get("issuer") or "").strip()
    card_digits = "".join(c for c in card if c.isdigit())
    if len(card_digits) >= 13:
        return {"card_number": card_digits[:19], "owner": owner, "bank": bank}
    if phone:
        digits = "".join(c for c in phone if c.isdigit())
        formatted = phone if phone.startswith("+") else (f"+{digits}" if digits else phone)
        return {"phone": formatted, "owner": owner, "bank": bank}
    if wallet:
        return {"phone": wallet, "owner": owner, "bank": bank}
    return {}


def prochub_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import ProchubPayInSession
    from payments.psp_payin import requisite_payload_has_fields

    s = ProchubPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = prochub_map_requisite(s.create_response or {})
    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = prochub_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def try_attach_prochub_session(pay_in: Any) -> bool | None:
    from payments.models import ProchubPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_prochub_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    external_id = str(pay_in.id)
    ps_name = pay_in.payment_system.name if pay_in.payment_system else None
    session, _ = ProchubPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={
            "external_id": external_id,
            "notification_token": secrets.token_urlsafe(24),
            "create_response": {},
            "last_webhook_payload": {},
        },
    )
    if not session.notification_token:
        session.notification_token = secrets.token_urlsafe(24)
    session.external_id = external_id
    session.save(update_fields=["external_id", "notification_token", "updated_at"])

    bank_code = (getattr(settings, "PROCHUB_BANK_CODE", None) or "").strip() or None
    ok, data = prochub_create_invoice(
        amount=pay_in.amount,
        internal_id=external_id,
        callback_url=prochub_callback_url(),
        callback_key=session.notification_token,
        invoice_type=prochub_invoice_type_for(ps_name),
        bank_code=bank_code,
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Prochub create invoice failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    session.provider_invoice_id = str((session.create_response or {}).get("invoiceId") or "")
    session.save(update_fields=["create_response", "provider_invoice_id", "updated_at"])

    req = prochub_map_requisite(session.create_response)
    if not req:
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Prochub: no requisite PayIn=%s", pay_in.id)
        return False
    return True


def prochub_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import ProchubPayInSession

    try:
        s = ProchubPayInSession.objects.get(pay_in=pay_in)
    except ProchubPayInSession.DoesNotExist:
        return
    if not s.provider_invoice_id:
        return
    ok, data = prochub_cancel_invoice(invoice_id=s.provider_invoice_id, pay_in=pay_in)
    if not ok:
        logger.warning("Prochub cancel failed PayIn=%s invoice=%s: %s", pay_in.id, s.provider_invoice_id, data)
