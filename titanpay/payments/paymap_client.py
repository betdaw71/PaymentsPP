"""HTTP client for PayMap PSP (API v2, KZT / fiat invoice). Docs: https://docs.paymap.me (use HTTP if TLS fails)."""
from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def paymap_trader_username() -> str:
    return getattr(settings, "PAYMAP_TRADER_USERNAME", "paymap_kzt")


def is_paymap_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == paymap_trader_username()


def paymap_callback_url() -> str:
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/paymap/"


def _api_base() -> str:
    return (getattr(settings, "PAYMAP_API_BASE", "https://paymap.co") or "").rstrip("/")


def _api_key() -> str:
    return (getattr(settings, "PAYMAP_API_KEY", None) or "").strip()


def _invoice_type_map() -> dict[str, str]:
    raw = getattr(settings, "PAYMAP_INVOICE_TYPE_MAP", None)
    if isinstance(raw, dict):
        return {str(k): str(v).strip().upper() for k, v in raw.items() if str(v).strip()}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v).strip().upper() for k, v in parsed.items() if str(v).strip()}
        except json.JSONDecodeError:
            logger.warning("PAYMAP_INVOICE_TYPE_MAP is not valid JSON")
    default = (getattr(settings, "PAYMAP_DEFAULT_INVOICE_TYPE", None) or "CARD").strip().upper()
    return {"__default__": default}


def invoice_type_for_payment_system(ps_name: str) -> str:
    mapping = _invoice_type_map()
    if ps_name in mapping:
        return mapping[ps_name]
    return mapping.get("__default__", "CARD")


def _target_bank_for_ps(ps_name: str) -> str | None:
    raw = getattr(settings, "PAYMAP_TARGET_BANK_MAP", None)
    if isinstance(raw, dict):
        val = raw.get(ps_name) or raw.get(ps_name.upper())
        if val:
            return str(val).strip()
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                val = parsed.get(ps_name) or parsed.get(ps_name.upper())
                if val:
                    return str(val).strip()
        except json.JSONDecodeError:
            pass
    return None


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "apikey": _api_key(),
    }


def _request_get(
    path: str,
    *,
    params: dict[str, Any],
    timeout: int = 60,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    key = _api_key()
    if not key:
        return False, "PAYMAP_API_KEY is empty"
    base = _api_base()
    if not base:
        return False, "PAYMAP_API_BASE is empty"
    url = f"{base}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urlencode(params)}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.PAYMAP_OUT_REQUEST,
        body=params,
        http_method="GET",
        url=url.split("?")[0],
        note=f"query={params}",
    )
    try:
        r = requests.get(url, headers=_headers(), timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("PayMap GET %s failed: %s", path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.PAYMAP_OUT_RESPONSE,
            body={"error": str(exc)},
            http_method="GET",
            url=url.split("?")[0],
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
        direction=Direction.PAYMAP_OUT_RESPONSE,
        body=resp_body if isinstance(resp_body, dict) else {"payload": resp_body},
        http_method="GET",
        url=url.split("?")[0],
        status_code=r.status_code,
        note="PayMap API",
    )
    if not r.ok:
        return False, resp_body if isinstance(resp_body, dict) else {"error": str(resp_body)}
    if isinstance(resp_body, dict) and resp_body.get("ok") is False:
        return False, resp_body
    return True, resp_body if isinstance(resp_body, dict) else {"payload": resp_body}


def paymap_create_fiat_invoice(
    *,
    amount: Decimal,
    currency: str,
    invoice_type: str,
    partner_invoice_id: str,
    callback_url: str | None = None,
    back_url: str | None = None,
    target_bank: str | None = None,
    life_time_minutes: int | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    params: dict[str, Any] = {
        "amount": float(amount),
        "invoiceType": invoice_type.upper(),
        "currency": currency.upper(),
        "partnerInvoiceId": partner_invoice_id,
        "callbackUrl": callback_url or paymap_callback_url(),
        "force": "true",
    }
    if back_url:
        params["backUrl"] = back_url
    if target_bank:
        params["targetBank"] = target_bank
    lifetime = life_time_minutes or int(getattr(settings, "PAYMAP_INVOICE_LIFETIME_MINUTES", 15) or 15)
    params["lifeTime"] = lifetime
    return _request_get("/api/v2/invoice/fiat/create", params=params, pay_in=pay_in)


def paymap_map_requisite(create_body: dict) -> dict:
    if not isinstance(create_body, dict):
        return {}
    data = create_body.get("data") if create_body.get("ok") is not False else create_body
    if not isinstance(data, dict):
        data = create_body
    creds = data.get("credentials") or {}
    if not isinstance(creds, dict):
        creds = {}
    req: dict[str, Any] = {}
    wallet = (creds.get("wallet") or "").strip()
    if wallet:
        digits = "".join(c for c in wallet if c.isdigit())
        if len(digits) >= 16:
            req["card_number"] = digits[:16]
        elif len(digits) >= 10:
            req["phone"] = f"+{digits}" if not wallet.startswith("+") else wallet
        else:
            req["deposit_number"] = wallet
    holder = (creds.get("holder") or "").strip()
    if holder:
        req["owner"] = holder
    bank = (creds.get("bank") or "").strip()
    if bank:
        req["bank"] = bank
    deeplink = (creds.get("deeplink") or "").strip()
    if deeplink:
        req["deeplink"] = deeplink
    return req


def paymap_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import PaymapPayInSession
    from payments.psp_payin import requisite_payload_has_fields

    s = PaymapPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = paymap_map_requisite(s.create_response or {})
    if requisite_payload_has_fields(req) or req.get("deeplink"):
        return req
    return None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = paymap_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def _invoice_id_from_webhook(body: dict) -> str:
    for key in (
        "deposit_request_card_uuid",
        "deposit_request_sbp_uuid",
        "deposit_request_bank_account_uuid",
        "deposit_request_nspk_uuid",
        "invoice_id",
    ):
        val = body.get(key)
        if val:
            return str(val).strip()
    return ""


def paymap_webhook_outcome(body: dict) -> str | None:
    """success | fail | None."""
    status = (body.get("status") or "").strip().lower()
    if status in ("completed", "payed", "paid", "success", "finished"):
        return "success"
    if status in ("canceled", "cancelled", "expired", "failed", "declined"):
        return "fail"
    return None


def try_attach_paymap_session(pay_in: Any) -> bool | None:
    from payments.models import PaymapPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps, requisite_payload_has_fields

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_paymap_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    ps_name = pay_in.payment_system.name if pay_in.payment_system else ""
    invoice_type = invoice_type_for_payment_system(ps_name)
    currency_sym = (pay_in.currency.symbol or "KZT").strip().upper() if pay_in.currency else "KZT"
    partner_id = str(pay_in.id)
    target_bank = _target_bank_for_ps(ps_name)

    session, _ = PaymapPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": partner_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = partner_id
    session.payment_system_name = ps_name
    session.save(update_fields=["external_id", "payment_system_name", "updated_at"])

    ok, data = paymap_create_fiat_invoice(
        amount=pay_in.amount,
        currency=currency_sym,
        invoice_type=invoice_type,
        partner_invoice_id=partner_id,
        target_bank=target_bank,
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("PayMap create invoice failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    inner = (session.create_response or {}).get("data") or {}
    if isinstance(inner, dict):
        session.provider_invoice_id = str(inner.get("invoice_id") or "")
    session.save(update_fields=["create_response", "provider_invoice_id", "updated_at"])

    req = paymap_map_requisite(session.create_response)
    if not requisite_payload_has_fields(req) and not req.get("deeplink"):
        session.create_response = {
            "error": "no_credentials_in_response",
            "upstream": session.create_response,
        }
        session.provider_invoice_id = ""
        session.save(update_fields=["create_response", "provider_invoice_id", "updated_at"])
        logger.error("PayMap: no requisite PayIn=%s ps=%s", pay_in.id, ps_name)
        return False
    return True


def paymap_cancel_if_linked(pay_in: Any) -> None:
    """PayMap: cancel via POST change_status when configured (optional)."""
    from payments.models import PaymapPayInSession

    try:
        s = PaymapPayInSession.objects.get(pay_in=pay_in)
    except PaymapPayInSession.DoesNotExist:
        return
    if not s.provider_invoice_id:
        return
    if not getattr(settings, "PAYMAP_CANCEL_ON_DECLINE", False):
        logger.info("PayMap cancel skipped PayIn=%s (PAYMAP_CANCEL_ON_DECLINE=false)", pay_in.id)
        return
    _request_post_change_status(invoice_id=s.provider_invoice_id, status="Canceled", pay_in=pay_in)


def _request_post_change_status(*, invoice_id: str, status: str, pay_in=None) -> None:
    key = _api_key()
    base = _api_base()
    if not key or not base:
        return
    url = f"{base}/api/v2/invoice/change_status?invoice_id={invoice_id}"
    from payments.payin_trace import Direction, trace_log

    body = {"status": status}
    trace_log(
        pay_in=pay_in,
        direction=Direction.PAYMAP_OUT_REQUEST,
        body=body,
        http_method="POST",
        url=url,
        note="change_status",
    )
    try:
        r = requests.post(url, json=body, headers=_headers(), timeout=30)
        resp = r.json() if r.content else {}
    except requests.RequestException as exc:
        resp = {"error": str(exc)}
        r = None
    trace_log(
        pay_in=pay_in,
        direction=Direction.PAYMAP_OUT_RESPONSE,
        body=resp,
        http_method="POST",
        url=url,
        status_code=r.status_code if r is not None else None,
        note="change_status",
    )
