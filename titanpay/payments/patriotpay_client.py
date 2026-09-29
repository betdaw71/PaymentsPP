"""HTTP client for PatriotPay PSP (https://api.patriotpay.club, H2H Scenario A)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def patriotpay_trader_username() -> str:
    return getattr(settings, "PATRIOTPAY_TRADER_USERNAME", "patriot1")


def is_patriotpay_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == patriotpay_trader_username()


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


def _opt_str(raw) -> str | None:
    val = str(raw or "").strip()
    if not val or val.lower() in ("null", "none"):
        return None
    return val


def _setting_for_ps(map_name: str, default_name: str, ps_name: str | None) -> str | None:
    ps = (ps_name or "").strip()
    mapped = _parse_json_map(map_name)
    if ps and ps in mapped:
        return _opt_str(mapped[ps])
    return _opt_str(getattr(settings, default_name, None))


def patriotpay_payment_method_for(payment_system_name: str | None) -> str | None:
    return _setting_for_ps("PATRIOTPAY_PAYIN_METHOD_MAP", "PATRIOTPAY_PAYIN_METHOD", payment_system_name)


def patriotpay_payment_option_for(payment_system_name: str | None) -> str | None:
    return _setting_for_ps("PATRIOTPAY_PAYIN_OPTION_MAP", "PATRIOTPAY_PAYIN_OPTION", payment_system_name)


def patriotpay_cross_border_currency_for(
    payment_system_name: str | None,
    payin_currency: str | None = None,
) -> str | None:
    from_ps = _setting_for_ps(
        "PATRIOTPAY_CROSS_BORDER_CURRENCY_MAP",
        "PATRIOTPAY_CROSS_BORDER_CURRENCY",
        payment_system_name,
    )
    if from_ps:
        return from_ps
    by_payin = _parse_json_map("PATRIOTPAY_CROSS_BORDER_CURRENCY_BY_PAYIN")
    cur = (payin_currency or "").strip().upper()
    if cur and cur in by_payin:
        return _opt_str(by_payin[cur])
    return None


def patriotpay_cross_border_requisite_type_for(payment_system_name: str | None) -> str | None:
    return _setting_for_ps(
        "PATRIOTPAY_CROSS_BORDER_REQUISITE_TYPE_MAP",
        "PATRIOTPAY_CROSS_BORDER_REQUISITE_TYPE",
        payment_system_name,
    )


def patriotpay_callback_url() -> str:
    explicit = (getattr(settings, "PATRIOTPAY_CALLBACK_URL", None) or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/patriotpay/"


def _api_key() -> str:
    return (getattr(settings, "PATRIOTPAY_API_KEY", None) or "").strip()


def _secret_key() -> str:
    return (getattr(settings, "PATRIOTPAY_SECRET_KEY", None) or "").strip()


def _api_base() -> str:
    return (getattr(settings, "PATRIOTPAY_API_BASE", "https://api.patriotpay.club") or "").rstrip("/")


def _canonical_body(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _format_amount(amount: Decimal) -> str:
    d = Decimal(str(amount)).quantize(Decimal("0.01"))
    if d == d.to_integral_value():
        return str(int(d))
    return f"{d:.2f}"


def _sign_request(*, method: str, url: str, body: str = "") -> str:
    string_to_sign = f"{method.upper()}{url}{body}"
    digest = hmac.new(_secret_key().encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def _headers(*, method: str, url: str, body: str = "") -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Identity": _api_key(),
        "X-Signature": _sign_request(method=method, url=url, body=body),
    }


def verify_webhook_token(received_token: str | None, expected_token: str | None) -> bool:
    if getattr(settings, "PATRIOTPAY_WEBHOOK_SKIP_VERIFY", False):
        logger.warning("PatriotPay webhook: PATRIOTPAY_WEBHOOK_SKIP_VERIFY is enabled")
        return True
    recv = (received_token or "").strip()
    exp = (expected_token or "").strip()
    if not recv or not exp:
        return False
    return hmac.compare_digest(recv, exp)


def _unwrap_invoice_response(resp_body: Any) -> dict[str, Any] | None:
    if isinstance(resp_body, dict):
        return resp_body
    if isinstance(resp_body, list) and resp_body and isinstance(resp_body[0], dict):
        return resp_body[0]
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
        return False, "PATRIOTPAY_API_KEY is empty"
    if not _secret_key():
        return False, "PATRIOTPAY_SECRET_KEY is empty"
    base = _api_base()
    if not base:
        return False, "PATRIOTPAY_API_BASE is empty"

    payload = json_payload or {}
    body = _canonical_body(payload) if method.upper() != "GET" and send_json_body and payload else ""
    url = f"{base}/{path.lstrip('/')}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.PATRIOTPAY_OUT_REQUEST,
        body=payload if payload else {"_method": method, "_path": path},
        http_method=method,
        url=url,
        note="PatriotPay API",
    )
    try:
        headers = _headers(method=method, url=url, body=body)
        if method.upper() == "GET" or not body:
            r = requests.request(method, url, headers=headers, timeout=timeout)
        else:
            r = requests.request(method, url, data=body.encode("utf-8"), headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("PatriotPay %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.PATRIOTPAY_OUT_RESPONSE,
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
        direction=Direction.PATRIOTPAY_OUT_RESPONSE,
        body=resp_body,
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="PatriotPay API",
    )
    if not r.ok:
        return False, resp_body if isinstance(resp_body, dict) else {"error": str(resp_body)}
    if isinstance(resp_body, list):
        return True, {"items": resp_body}
    invoice = _unwrap_invoice_response(resp_body)
    if invoice is None:
        return False, {"error": "unexpected_response_shape", "upstream": resp_body}
    return True, invoice


def patriotpay_create_invoice(
    *,
    amount: Decimal,
    internal_id: str,
    currency: str,
    notification_url: str,
    notification_token: str,
    user_id: str | None = None,
    payment_method: str | None = None,
    payment_option: str | None = None,
    cross_border_currency: str | None = None,
    cross_border_requisite_type: str | None = None,
    success_url: str | None = None,
    cancel_url: str | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    payload: dict[str, Any] = {
        "type": "in",
        "amount": _format_amount(amount),
        "currency": currency.upper(),
        "notificationUrl": notification_url,
        "notificationToken": notification_token,
        "internalId": internal_id,
        "userId": user_id or internal_id,
        "startDeal": True,
        "strictlySingleTransfer": True,
        "paymentOption": payment_option or "CROSS_BORDER",
        "paymentMethod": payment_method,
    }
    option = str(payload["paymentOption"] or "").upper()
    if option == "CROSS_BORDER":
        payload["crossBorderCurrency"] = (cross_border_currency or "").upper() or None
        payload["crossBorderRequisiteType"] = cross_border_requisite_type
    if success_url:
        payload["successUrl"] = success_url
    if cancel_url:
        payload["cancelUrl"] = cancel_url
    return _request("POST", "/api/merchant/invoices", json_payload=payload, pay_in=pay_in)


def patriotpay_cancel_invoice(*, invoice_id: str, pay_in=None) -> tuple[bool, dict[str, Any] | str]:
    invoice_id = (invoice_id or "").strip()
    if not invoice_id:
        return False, "invoice_id is empty"
    return _request(
        "POST",
        f"/api/merchant/invoices/{invoice_id}/cancel",
        json_payload=None,
        send_json_body=False,
        pay_in=pay_in,
    )


def patriotpay_get_payment_methods(*, currency: str = "KZT") -> tuple[bool, dict[str, Any] | str]:
    cur = (currency or "KZT").strip().upper()
    return _request("GET", f"/api/merchant/payment-methods?currency={cur}", pay_in=None)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _invoice_from_webhook(body: dict) -> dict:
    invoice = body.get("invoice")
    return invoice if isinstance(invoice, dict) else body


def resolve_patriotpay_webhook_session(
    *,
    internal_id: str | None,
    invoice_id: str | None,
    deal_id: str | None = None,
):
    """Найти (или восстановить) PatriotpayPayInSession по internalId / invoice id."""
    from payments.models import PayIn, PatriotpayPayInSession

    iid = (internal_id or "").strip()
    inv_id = (invoice_id or "").strip()
    did = (deal_id or "").strip()

    if iid:
        session = (
            PatriotpayPayInSession.objects.filter(external_id=iid)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session is not None:
            return session

    if inv_id:
        session = (
            PatriotpayPayInSession.objects.filter(provider_invoice_id=inv_id)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session is not None:
            return session

    if did:
        session = (
            PatriotpayPayInSession.objects.filter(provider_deal_id=did)
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
    if not is_patriotpay_trader(pay_in.order.payment_details.group.trader):
        return None

    token = secrets.token_urlsafe(24)
    session, created = PatriotpayPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={
            "external_id": str(pay_in.id),
            "notification_token": token,
            "create_response": {},
            "last_webhook_payload": {},
        },
    )
    updates: list[str] = []
    if str(session.external_id) != str(pay_in.id):
        session.external_id = str(pay_in.id)
        updates.append("external_id")
    if inv_id and not session.provider_invoice_id:
        session.provider_invoice_id = inv_id
        updates.append("provider_invoice_id")
    if did and not session.provider_deal_id:
        session.provider_deal_id = did
        updates.append("provider_deal_id")
    if not session.notification_token:
        session.notification_token = token
        updates.append("notification_token")
    if updates:
        updates.append("updated_at")
        session.save(update_fields=updates)
    if created:
        logger.info("PatriotPay webhook: recovered session for PayIn=%s internalId=%s", pay_in.id, iid)
    return session


def patriotpay_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (ignore intermediate)."""
    invoice = _invoice_from_webhook(body)
    status = _norm_status(invoice.get("status"))
    if status in ("paid", "recalculated", "recalculation", "re_calculation"):
        return "success"
    if status in ("canceled", "cancelled", "expired"):
        return "fail"
    return None


def patriotpay_is_webhook_body(body: dict | None) -> bool:
    """True for PatriotPay IPN (invoice.internalId / invoice.id)."""
    if not isinstance(body, dict):
        return False
    nested = body.get("invoice")
    if isinstance(nested, dict):
        return bool(nested.get("internalId") or nested.get("id"))
    return bool(body.get("internalId"))


def _positive_decimal(raw) -> Decimal | None:
    if raw is None:
        return None
    try:
        val = Decimal(str(raw).strip().replace(",", "."))
    except (ValueError, TypeError, ArithmeticError):
        return None
    return val if val > 0 else None


def _amount_from_source(source: dict) -> Decimal | None:
    if not isinstance(source, dict):
        return None
    for key in (
        "paidAmount",
        "paid_amount",
        "factAmount",
        "fact_amount",
        "receivedAmount",
        "amount",
    ):
        paid = _positive_decimal(source.get(key))
        if paid is not None:
            return paid
    for nested_key in ("sum", "receivedSumFromTaker", "receivedSumFromMaker"):
        nested = source.get(nested_key)
        if isinstance(nested, dict):
            paid = _positive_decimal(nested.get("amount"))
            if paid is not None:
                return paid
    return None


def patriotpay_webhook_paid_amount(body: dict | None) -> Decimal | None:
    """Фактическая сумма из IPN PatriotPay: invoice.sum.amount / amount."""
    if not patriotpay_is_webhook_body(body):
        return None
    assert isinstance(body, dict)
    invoice = _invoice_from_webhook(body)
    deal = invoice.get("deal") if isinstance(invoice.get("deal"), dict) else {}
    for source in (invoice, deal, body):
        paid = _amount_from_source(source)
        if paid is not None:
            return paid
    return None


def patriotpay_success_webhook_allows_completed_recalc(body: dict | None) -> bool:
    """Повторный paid после Completed — можно скорректировать сумму."""
    if not isinstance(body, dict):
        return False
    return patriotpay_is_webhook_body(body) and patriotpay_webhook_outcome(body) == "success"


def _first_deal(create_body: dict) -> dict:
    deals = create_body.get("deals")
    if isinstance(deals, list) and deals and isinstance(deals[0], dict):
        return deals[0]
    deal = create_body.get("deal")
    return deal if isinstance(deal, dict) else {}


def patriotpay_map_requisite(create_body: dict) -> dict:
    """Маппинг deals[].requisites / paymentRequisites из POST /api/merchant/invoices."""
    body = create_body if isinstance(create_body, dict) else {}
    deal = _first_deal(body)
    requisites = deal.get("requisites") if isinstance(deal, dict) else {}
    if not isinstance(requisites, dict):
        requisites = {}
    if not requisites and isinstance(body.get("paymentRequisites"), dict):
        requisites = body.get("paymentRequisites") or {}
    address = (
        (
            requisites.get("requisites")
            or requisites.get("phone")
            or requisites.get("card")
            or requisites.get("cardNumber")
            or ""
        )
        .strip()
    )
    owner = requisites.get("holder") or requisites.get("owner") or ""
    bank = (
        (deal.get("paymentMethod") if isinstance(deal, dict) else None)
        or body.get("paymentMethod")
        or requisites.get("bank")
        or ""
    )
    qr = ""
    if isinstance(deal, dict):
        qr = (deal.get("qrCodeLink") or "").strip()
    if not address:
        if qr:
            return {"payment_form_url": qr, "owner": owner, "bank": bank}
        return {}
    digits = "".join(c for c in address if c.isdigit())
    payment_option = (
        (deal.get("paymentOption") if isinstance(deal, dict) else None)
        or body.get("paymentOption")
        or ""
    )
    payment_option = str(payment_option).strip().upper()
    req_type = str(
        (deal.get("crossBorderRequisiteType") if isinstance(deal, dict) else None)
        or body.get("crossBorderRequisiteType")
        or ""
    ).strip().upper()
    if req_type == "PHONE" or (payment_option == "CROSS_BORDER" and len(digits) <= 12):
        phone = address if address.startswith("+") else (f"+{digits}" if digits else address)
        return {"phone": phone, "owner": owner, "bank": bank}
    if address.startswith("+") or (digits and len(digits) <= 12):
        return {"phone": address if address.startswith("+") else f"+{digits}", "owner": owner, "bank": bank}
    if len(digits) >= 16:
        return {"card_number": digits[:16], "owner": owner, "bank": bank}
    return {"card_number": address, "owner": owner, "bank": bank}


def patriotpay_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import PatriotpayPayInSession

    s = PatriotpayPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = patriotpay_map_requisite(s.create_response or {})
    from payments.psp_payin import requisite_payload_has_fields

    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = patriotpay_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def try_attach_patriotpay_session(pay_in: Any) -> bool | None:
    """PatriotPay API для виртуальной группы patriot1 (H2H Scenario A)."""
    from payments.models import PatriotpayPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_patriotpay_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    currency_sym = (pay_in.currency.symbol or "KZT").strip().upper() if pay_in.currency else "KZT"
    external_id = str(pay_in.id)
    ps_name = pay_in.payment_system.name if pay_in.payment_system else None

    session, created = PatriotpayPayInSession.objects.get_or_create(
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

    payer_user_id = str(pay_in.id)
    if getattr(settings, "PATRIOTPAY_PAYER_USER_ID_FROM_CLIENT", False):
        if pay_in.client_id and getattr(pay_in, "client", None):
            payer_user_id = str(pay_in.client.client_id)

    ok, data = patriotpay_create_invoice(
        amount=pay_in.amount,
        internal_id=external_id,
        currency=currency_sym,
        notification_url=patriotpay_callback_url(),
        notification_token=session.notification_token,
        user_id=payer_user_id,
        payment_method=patriotpay_payment_method_for(ps_name),
        payment_option=patriotpay_payment_option_for(ps_name),
        cross_border_currency=patriotpay_cross_border_currency_for(ps_name, currency_sym),
        cross_border_requisite_type=patriotpay_cross_border_requisite_type_for(ps_name),
        success_url=(getattr(pay_in, "success_url", None) or None),
        cancel_url=(getattr(pay_in, "failed_url", None) or None),
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("PatriotPay create invoice failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    session.provider_invoice_id = str((session.create_response or {}).get("id") or "")
    deal = _first_deal(session.create_response)
    session.provider_deal_id = str(deal.get("id") or "")
    session.save(
        update_fields=["create_response", "provider_invoice_id", "provider_deal_id", "updated_at"]
    )

    req = patriotpay_map_requisite(session.create_response)
    deals = (session.create_response or {}).get("deals")
    if not req and isinstance(deals, list) and len(deals) == 0:
        session.create_response = {
            "error": "no_free_requisites",
            "upstream": session.create_response,
        }
        session.provider_invoice_id = ""
        session.provider_deal_id = ""
        session.save(update_fields=["create_response", "provider_invoice_id", "provider_deal_id", "updated_at"])
        logger.error("PatriotPay: empty deals PayIn=%s", pay_in.id)
        return False
    if not req:
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("PatriotPay: no requisite PayIn=%s", pay_in.id)
        return False
    return True


def patriotpay_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import PatriotpayPayInSession

    try:
        s = PatriotpayPayInSession.objects.get(pay_in=pay_in)
    except PatriotpayPayInSession.DoesNotExist:
        return
    if not s.provider_invoice_id:
        return
    ok, data = patriotpay_cancel_invoice(invoice_id=s.provider_invoice_id, pay_in=pay_in)
    if not ok:
        logger.warning(
            "PatriotPay cancel failed PayIn=%s invoice=%s: %s",
            pay_in.id,
            s.provider_invoice_id,
            data,
        )
