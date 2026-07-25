"""HTTP client for Concored / ProcessorCore PSP (Myanmar MMK, H2H pay-in)."""
from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def concored_trader_username() -> str:
    return getattr(settings, "CONCORDED_TRADER_USERNAME", "concored_mmk")


def is_concored_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == concored_trader_username()


def concored_callback_url() -> str:
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/concored/"


def _api_base() -> str:
    return (getattr(settings, "CONCORDED_API_BASE", "") or "").rstrip("/")


def _token_map() -> dict[str, str]:
    """JWT Bearer per PaymentSystem name (KBZPay, WavePay)."""
    raw = getattr(settings, "CONCORDED_TOKEN_MAP", None)
    if isinstance(raw, dict):
        return {str(k): str(v).strip() for k, v in raw.items() if str(v).strip()}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v).strip() for k, v in parsed.items() if str(v).strip()}
        except json.JSONDecodeError:
            logger.warning("CONCORDED_TOKEN_MAP is not valid JSON")
    tokens: dict[str, str] = {}
    kbz = (getattr(settings, "CONCORDED_KBZPAY_TOKEN", None) or "").strip()
    wave = (getattr(settings, "CONCORDED_WAVEPAY_TOKEN", None) or "").strip()
    if kbz:
        tokens["KBZPay"] = kbz
    if wave:
        tokens["WavePay"] = wave
    return tokens


def _payment_method_map() -> dict[str, str]:
    raw = getattr(settings, "CONCORDED_PAYMENT_METHOD_MAP", None)
    if isinstance(raw, dict):
        return {str(k): str(v).strip() for k, v in raw.items() if str(v).strip()}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v).strip() for k, v in parsed.items() if str(v).strip()}
        except json.JSONDecodeError:
            logger.warning("CONCORDED_PAYMENT_METHOD_MAP is not valid JSON")
    return {}


def token_for_payment_system(ps_name: str) -> str:
    return _token_map().get(ps_name, "").strip()


def payment_method_for_payment_system(ps_name: str) -> str | None:
    code = _payment_method_map().get(ps_name, "").strip()
    return code or None


def _looks_like_jwt(value: str) -> bool:
    v = (value or "").strip()
    return v.count(".") == 2 and v.startswith("eyJ")


def _response_is_html(payload: dict[str, Any]) -> bool:
    raw = payload.get("raw")
    if not isinstance(raw, str):
        return False
    head = raw.lstrip()[:64].lower()
    return head.startswith("<!doctype") or head.startswith("<html")


def _amount_minor(amount: Decimal) -> int:
    factor = getattr(settings, "CONCORDED_AMOUNT_MINOR_FACTOR", 1)
    try:
        mult = Decimal(str(factor))
    except (InvalidOperation, ValueError, TypeError):
        mult = Decimal("1")
    val = (amount * mult).quantize(Decimal("1"))
    if val <= 0:
        raise ValueError("amount must be positive")
    return int(val)


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def _request(
    method: str,
    path: str,
    *,
    token: str,
    json_payload: dict | None = None,
    timeout: int = 60,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    if not token:
        return False, "Concored merchant token is empty"
    base = _api_base()
    if not base:
        return False, "CONCORDED_API_BASE is empty"
    url = f"{base}/{path.lstrip('/')}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.CONCORDED_OUT_REQUEST,
        body=json_payload or {},
        http_method=method,
        url=url,
        note="Concored API",
    )
    try:
        r = requests.request(method, url, json=json_payload, headers=_headers(token), timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("Concored %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.CONCORDED_OUT_RESPONSE,
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
        direction=Direction.CONCORDED_OUT_RESPONSE,
        body=resp_body if isinstance(resp_body, dict) else {"payload": resp_body},
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="Concored API",
    )
    if not isinstance(resp_body, dict):
        return False, {"error": str(resp_body)}
    if not r.ok:
        return False, resp_body
    if _response_is_html(resp_body):
        return False, {
            "error": "non_json_response",
            "message": (
                "Concored returned HTML instead of JSON — check CONCORDED_API_BASE "
                "(do not use the marketing site URL, e.g. https://concored.com)"
            ),
            "upstream": resp_body,
        }
    if path.rstrip("/").endswith("/payments") and r.ok and "paymentIntentId" not in resp_body:
        return False, {
            "error": "invalid_create_response",
            "message": "Expected paymentIntentId in JSON body",
            "upstream": resp_body,
        }
    return True, resp_body


def concored_create_payment(
    *,
    token: str,
    amount: Decimal,
    external_order_id: str,
    external_client_id: str,
    payment_method: str,
    currency: str,
    callback_url: str | None = None,
    traffic_type: str | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    payload: dict[str, Any] = {
        "externalOrderId": external_order_id,
        "externalClientId": external_client_id,
        "paymentMethod": payment_method,
        "amount": _amount_minor(amount),
        "currency": currency.upper(),
        "callbackUrl": callback_url or concored_callback_url(),
    }
    if traffic_type:
        payload["trafficType"] = traffic_type
    return _request("POST", "/api/v1/payments", token=token, json_payload=payload, pay_in=pay_in)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().upper()


def concored_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (ignore intermediate)."""
    event = (body.get("EventType") or body.get("eventType") or "").strip().lower()
    if event == "payment.succeeded":
        return "success"
    if event in ("payment.failed", "payment.canceled", "payment.expired"):
        return "fail"
    status = _norm_status(body.get("Status") or body.get("status"))
    if status == "SUCCEEDED":
        return "success"
    if status in ("FAILED", "CANCELED", "EXPIRED"):
        return "fail"
    return None


def _format_phone(raw: Any) -> str | None:
    if raw is None:
        return None
    digits = "".join(c for c in str(raw) if c.isdigit())
    if not digits:
        return None
    if digits.startswith("95"):
        return f"+{digits}"
    return f"+{digits}" if str(raw).startswith("+") else digits


def concored_map_requisite(create_body: dict) -> dict:
    """Маппинг paymentDetails из POST /api/v1/payments в payment_details для мерчанта."""
    if not isinstance(create_body, dict):
        return {}
    details = create_body.get("paymentDetails") or create_body.get("payment_details") or {}
    if not isinstance(details, dict):
        return {}
    req: dict[str, Any] = {}
    card = (details.get("cardNumber") or details.get("card_number") or "").strip()
    if card:
        req["card_number"] = "".join(c for c in card if c.isdigit()) or card
    phone = _format_phone(details.get("phone"))
    if phone:
        req["phone"] = phone
    bank_account = (details.get("bankAccount") or details.get("bank_account") or "").strip()
    if bank_account:
        req["deposit_number"] = bank_account
    owner = (details.get("recipientName") or details.get("recipient_name") or "").strip()
    if owner:
        req["owner"] = owner
    deeplink = (details.get("deeplink") or "").strip()
    if deeplink:
        req["deeplink"] = deeplink
    qr = (details.get("qrImageUrl") or details.get("qr_image_url") or "").strip()
    if qr:
        req["qr_image_url"] = qr
    form_url = (create_body.get("paymentFormUrl") or create_body.get("payment_form_url") or "").strip()
    if form_url and not req.get("deeplink"):
        req["payment_form_url"] = form_url
    return req


def concored_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import ConcoredPayInSession

    s = ConcoredPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = concored_map_requisite(s.create_response or {})
    from payments.psp_payin import requisite_payload_has_fields

    if requisite_payload_has_fields(req):
        return req
    if req.get("deeplink") or req.get("payment_form_url") or req.get("qr_image_url"):
        return req
    return None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = concored_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def try_attach_concored_session(pay_in: Any) -> bool | None:
    """Concored API для виртуальной группы concored_mmk (KBZPay / WavePay)."""
    from payments.models import ConcoredPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps, requisite_payload_has_fields

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_concored_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    ps_name = pay_in.payment_system.name if pay_in.payment_system else ""
    token = token_for_payment_system(ps_name)
    payment_method = payment_method_for_payment_system(ps_name)
    if not token:
        logger.error("Concored: no token for payment_system=%s", ps_name)
        return False
    if not payment_method:
        logger.error("Concored: no paymentMethod mapping for payment_system=%s", ps_name)
        return False
    if _looks_like_jwt(payment_method):
        logger.error(
            "Concored: CONCORDED_PAYMENT_METHOD_MAP[%s] looks like a JWT; "
            "put the merchant token in CONCORDED_KBZPAY_TOKEN / CONCORDED_WAVEPAY_TOKEN "
            "and the payment method code from Concored in CONCORDED_PAYMENT_METHOD_MAP",
            ps_name,
        )
        return False

    currency_sym = (pay_in.currency.symbol or "MMK").strip().upper() if pay_in.currency else "MMK"
    external_id = str(pay_in.id)
    client_id = external_id
    if pay_in.client_id and getattr(pay_in, "client", None):
        client_id = str(pay_in.client.client_id)

    traffic_type = None
    order = pay_in.order
    if order and order.solution is not None and getattr(order.solution, "ftd", False):
        traffic_type = "FTD"

    session, _ = ConcoredPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": external_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = external_id
    session.payment_system_name = ps_name
    session.save(update_fields=["external_id", "payment_system_name", "updated_at"])

    ok, data = concored_create_payment(
        token=token,
        amount=pay_in.amount,
        external_order_id=external_id,
        external_client_id=client_id,
        payment_method=payment_method,
        currency=currency_sym,
        traffic_type=traffic_type,
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Concored create payment failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    session.provider_payment_id = str(
        (session.create_response or {}).get("paymentIntentId")
        or (session.create_response or {}).get("payment_intent_id")
        or ""
    )
    session.save(update_fields=["create_response", "provider_payment_id", "updated_at"])

    req = concored_map_requisite(session.create_response)
    has_h2h = requisite_payload_has_fields(req) or bool(
        req.get("deeplink") or req.get("payment_form_url") or req.get("qr_image_url")
    )
    if not has_h2h:
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.provider_payment_id = ""
        session.save(update_fields=["create_response", "provider_payment_id", "updated_at"])
        logger.error("Concored: no requisite PayIn=%s ps=%s", pay_in.id, ps_name)
        return False
    return True


def concored_cancel_if_linked(pay_in: Any) -> None:
    """Concored Public API не документирует cancel pay-in — no-op."""
    from payments.models import ConcoredPayInSession

    try:
        s = ConcoredPayInSession.objects.get(pay_in=pay_in)
    except ConcoredPayInSession.DoesNotExist:
        return
    if s.provider_payment_id:
        logger.info(
            "Concored cancel skipped PayIn=%s paymentIntentId=%s (no cancel in Public API)",
            pay_in.id,
            s.provider_payment_id,
        )
