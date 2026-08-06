"""HTTP client for PlutusPay PSP (https://plutuspay.top/docs, Merchant API v2)."""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def plutus_trader_username() -> str:
    return getattr(settings, "PLUTUS_TRADER_USERNAME", "plutus1")


def is_plutus_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == plutus_trader_username()


def plutus_callback_url() -> str:
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/plutus/"


def _api_base() -> str:
    return (getattr(settings, "PLUTUS_API_BASE", "https://plutuspay.top") or "").rstrip("/")


def _api_key() -> str:
    return (getattr(settings, "PLUTUS_API_KEY", None) or "").strip()


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Api-Key": _api_key(),
    }


def _paymethod_map() -> dict[str, str]:
    raw = getattr(settings, "PLUTUS_PAYMETHOD_MAP", None)
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            logger.warning("PLUTUS_PAYMETHOD_MAP is not valid JSON")
    return {"C2C": "c2c", "C2CKZT": "c2c"}


def plutus_paymethod_for(payment_system_name: str) -> str:
    mapping = _paymethod_map()
    if payment_system_name in mapping:
        return mapping[payment_system_name]
    default = (getattr(settings, "PLUTUS_DEFAULT_PAYMETHOD", None) or "c2c").strip()
    return default


def _parse_response(r: requests.Response) -> tuple[bool, dict[str, Any] | str]:
    try:
        body = r.json() if r.content else {}
    except ValueError:
        body = {"raw": r.text[:2000]}
    if not isinstance(body, dict):
        return False, {"error": str(body)}
    if not r.ok:
        return False, body
    if body.get("status") == "error" or body.get("ok") is False:
        return False, body
    if body.get("success") is False:
        return False, body
    return True, body


def _request(
    method: str,
    path: str,
    *,
    json_payload: dict | None = None,
    timeout: int = 60,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    key = _api_key()
    if not key:
        return False, "PLUTUS_API_KEY is empty"
    base = _api_base()
    if not base:
        return False, "PLUTUS_API_BASE is empty"

    url = f"{base}/{path.lstrip('/')}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.PLUTUS_OUT_REQUEST,
        body=json_payload or {},
        http_method=method,
        url=url,
        note="Plutus API",
    )
    try:
        r = requests.request(method, url, json=json_payload, headers=_headers(), timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("Plutus %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.PLUTUS_OUT_RESPONSE,
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
        direction=Direction.PLUTUS_OUT_RESPONSE,
        body=body if isinstance(body, dict) else {"payload": body},
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="Plutus API",
    )
    return ok, body


def plutus_create_pay_in(
    *,
    amount: Decimal,
    external_id: str,
    paymethod: str,
    callback_url: str | None = None,
    client_id: str | None = None,
    contragent: bool | None = None,
    timeout_sec: int | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    """POST /merchant/v2/incoming/payment/create/"""
    amt = float(amount)
    if amt == int(amt):
        amt = int(amt)
    payload: dict[str, Any] = {
        "id": external_id,
        "amount": amt,
        "paymethod": paymethod,
        "timeout": int(timeout_sec or getattr(settings, "PLUTUS_PAYIN_TIMEOUT", 900) or 900),
        "callback_url": callback_url or plutus_callback_url(),
    }
    if client_id:
        payload["client_id"] = client_id
    use_contragent = contragent
    if use_contragent is None:
        use_contragent = getattr(settings, "PLUTUS_CONTRAGENT", False)
    if use_contragent:
        payload["contragent"] = True
    return _request("POST", "/merchant/v2/incoming/payment/create/", json_payload=payload, pay_in=pay_in)


def plutus_cancel_pay_in(external_id: str, *, pay_in=None) -> tuple[bool, dict[str, Any] | str]:
    """POST /merchant/v2/incoming/payment/cancel/"""
    if not external_id:
        return False, "empty external id"
    return _request(
        "POST",
        "/merchant/v2/incoming/payment/cancel/",
        json_payload={"id": external_id},
        pay_in=pay_in,
    )


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def plutus_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (service events / unknown)."""
    event = (body.get("event") or "").strip().lower()
    if event in ("requisite_deactivated", "capacity_available"):
        return None
    status = _norm_status(body.get("status"))
    if status == "completed":
        return "success"
    if status == "cancelled":
        return "fail"
    return None


def plutus_map_requisite(create_body: dict) -> dict:
    """platform.number — карта (c2c); sbp — телефон в number."""
    if not isinstance(create_body, dict):
        return {}
    platform = create_body.get("platform")
    if not isinstance(platform, dict):
        return {}
    owner = (platform.get("name") or "").strip()
    bank = (platform.get("bank") or "").strip()
    paymethod = _norm_status(platform.get("paymethod"))
    number = (platform.get("number") or "").strip()
    payment_url = (platform.get("payment_url") or "").strip()
    pay_page_url = (platform.get("pay_page_url") or "").strip()

    if paymethod in ("nspk", "vietqr") and payment_url:
        return {"payment_form_url": payment_url, "owner": owner, "bank": bank}
    if pay_page_url and not number:
        return {"payment_form_url": pay_page_url, "owner": owner, "bank": bank}

    if not number:
        return {}

    digits = "".join(c for c in number if c.isdigit())
    if platform.get("sbp") or paymethod == "sbp":
        phone = number if number.startswith("+") else f"+{digits}"
        return {"phone": phone, "owner": owner, "bank": bank}
    if len(digits) >= 13:
        return {"card_number": digits[:19], "owner": owner, "bank": bank}
    if number.startswith("+") or (digits and len(digits) <= 12):
        return {"phone": number if number.startswith("+") else f"+{digits}", "owner": owner, "bank": bank}
    return {"card_number": number, "owner": owner, "bank": bank}


def plutus_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import PlutusPayInSession
    from payments.psp_payin import requisite_payload_has_fields

    s = PlutusPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = plutus_map_requisite(s.create_response or {})
    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = plutus_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def plutus_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import PlutusPayInSession

    try:
        s = PlutusPayInSession.objects.get(pay_in=pay_in)
    except PlutusPayInSession.DoesNotExist:
        return
    ext = s.external_id or str(pay_in.id)
    ok, data = plutus_cancel_pay_in(ext, pay_in=pay_in)
    if not ok:
        logger.warning("Plutus cancel failed PayIn=%s detail=%s", pay_in.id, data)


def try_attach_plutus_session(pay_in: Any) -> bool | None:
    from payments.models import PlutusPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_plutus_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    ps_name = pay_in.payment_system.name if pay_in.payment_system else ""
    external_id = str(pay_in.id)
    paymethod = plutus_paymethod_for(ps_name)

    session, _ = PlutusPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": external_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = external_id
    session.payment_system_name = ps_name
    session.save(update_fields=["external_id", "payment_system_name", "updated_at"])

    client_id = None
    if getattr(pay_in, "client_id", None) and getattr(pay_in, "client", None):
        client_id = str(pay_in.client.client_id)

    ok, data = plutus_create_pay_in(
        amount=pay_in.amount,
        external_id=external_id,
        paymethod=paymethod,
        client_id=client_id,
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Plutus create pay-in failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    platform = (session.create_response or {}).get("platform")
    if isinstance(platform, dict):
        session.provider_trade_uuid = str(platform.get("trade_id") or "")
    session.save(update_fields=["create_response", "provider_trade_uuid", "updated_at"])

    req = plutus_map_requisite(session.create_response)
    if not req:
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.provider_trade_uuid = ""
        session.save(update_fields=["create_response", "provider_trade_uuid", "updated_at"])
        plutus_cancel_pay_in(external_id, pay_in=pay_in)
        logger.error("Plutus: no requisite PayIn=%s ps=%s", pay_in.id, ps_name)
        return False
    return True
