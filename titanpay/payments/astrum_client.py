"""HTTP client for Astrum PSP (KZT pay-out via Fernet-encrypted applications).

Docs: https://astrum.ac/api/redoc
Auth: Authorization: <API key>
Create payout: POST /source/v2/applications/new with Fernet(private_key).encrypt(json)
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

import requests
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)

_PAYOUT_SUCCESS = frozenset({"paid", "corrected", "success"})
_PAYOUT_FAIL = frozenset({"cancelled", "chargeback", "decline"})
_PAYIN_SUCCESS = frozenset({"auto_success", "hand_success", "corrected"})
_PAYIN_FAIL = frozenset({"auto_decline", "chargeback"})


def astrum_trader_username() -> str:
    return getattr(settings, "ASTRUM_TRADER_USERNAME", "astrum_kzt")


def is_astrum_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == astrum_trader_username()


def astrum_payment_system_name() -> str:
    return getattr(settings, "ASTRUM_C2C_NAME", "C2CKZT")


def astrum_payout_callback_url() -> str:
    explicit = (getattr(settings, "ASTRUM_CALLBACK_URL", None) or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/astrum/payout/"


def astrum_callback_url() -> str:
    """Alias for payout callback (backward compatible)."""
    return astrum_payout_callback_url()


def astrum_payin_callback_url() -> str:
    explicit = (getattr(settings, "ASTRUM_PAYIN_CALLBACK_URL", None) or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/astrum/payin/"


def _api_base() -> str:
    return (getattr(settings, "ASTRUM_API_BASE", None) or "https://astrum.ac/api").strip().rstrip("/")


def _api_key() -> str:
    return (getattr(settings, "ASTRUM_API_KEY", None) or "").strip()


def _private_key() -> str:
    return (getattr(settings, "ASTRUM_PRIVATE_KEY", None) or "").strip()


def _method_type_id() -> int | None:
    raw = getattr(settings, "ASTRUM_METHOD_TYPE_ID", None)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _method_name_id() -> int | None:
    raw = getattr(settings, "ASTRUM_METHOD_NAME_ID", None)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _currency() -> str:
    return (getattr(settings, "ASTRUM_CURRENCY", None) or "KZT").strip().upper() or "KZT"


def _express_default() -> bool:
    return bool(getattr(settings, "ASTRUM_EXPRESS", False))


def _fernet() -> Fernet | None:
    key = _private_key()
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except (ValueError, TypeError, InvalidToken) as exc:
        logger.error("Astrum Fernet key invalid: %s", exc)
        return None


def encrypt_application(payload: dict[str, Any]) -> str | None:
    """Fernet-encrypt payout/payin create payload → token string for encrypted_application."""
    f = _fernet()
    if f is None:
        return None
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return f.encrypt(body.encode("utf-8")).decode("utf-8")


def _headers() -> dict[str, str]:
    return {
        "accept": "application/json",
        "content-type": "application/json;charset=utf-8",
        "Authorization": _api_key(),
    }


def _request(
    method: str,
    path: str,
    *,
    json_payload: dict | None = None,
    params: dict | None = None,
    timeout: int = 60,
) -> tuple[bool, dict[str, Any] | str]:
    if not _api_key():
        return False, "ASTRUM_API_KEY is empty"
    base = _api_base()
    if not base:
        return False, "ASTRUM_API_BASE is empty"
    url = f"{base}/{path.lstrip('/')}"
    try:
        r = requests.request(
            method,
            url,
            json=json_payload,
            params=params,
            headers=_headers(),
            timeout=timeout,
        )
    except requests.RequestException as exc:
        logger.exception("Astrum %s %s failed: %s", method, path, exc)
        return False, str(exc)

    try:
        resp_body = r.json() if r.content else {}
    except ValueError:
        resp_body = {"raw": r.text[:2000]}

    if not isinstance(resp_body, dict):
        return False, {"error": str(resp_body), "http_status": r.status_code}

    if not r.ok:
        return False, resp_body if resp_body else {"error": f"http_{r.status_code}"}

    # Astrum: success=True is the business OK signal
    if resp_body.get("success") is False:
        return False, resp_body
    return True, resp_body


def astrum_get_methods() -> tuple[bool, dict[str, Any] | str]:
    return _request("GET", "/source/methods")


def astrum_get_info() -> tuple[bool, dict[str, Any] | str]:
    return _request("GET", "/source/info/api")


def astrum_get_balance() -> tuple[bool, dict[str, Any] | str]:
    return _request("GET", "/source/balance/api/currency")


def astrum_get_payout_info(foreign_id: str) -> tuple[bool, dict[str, Any] | str]:
    return _request("GET", "/source/v2/applications/info", params={"foreignId": foreign_id})


def astrum_create_payout(
    *,
    foreign_id: str,
    amount: Decimal | float | str,
    requisite: str,
    client_initials: str,
    method_type_id: int | None = None,
    method_name_id: int | None = None,
    express: bool | None = None,
    currency: str | None = None,
) -> tuple[bool, dict[str, Any] | str]:
    """POST /source/v2/applications/new (camelCase, new connections)."""
    mt = method_type_id if method_type_id is not None else _method_type_id()
    if mt is None:
        return False, "ASTRUM_METHOD_TYPE_ID is empty — run: python manage.py astrum_probe --methods"
    mn = method_name_id if method_name_id is not None else _method_name_id()
    payload: dict[str, Any] = {
        "foreignId": str(foreign_id),
        "amount": float(amount),
        "requisite": str(requisite).strip(),
        "methodTypeId": int(mt),
        "methodNameId": int(mn) if mn is not None else None,
        "clientInitials": (client_initials or "").strip() or "Client",
        "express": bool(_express_default() if express is None else express),
        "currency": (currency or _currency()).strip().upper() or None,
    }
    token = encrypt_application(payload)
    if not token:
        return False, "ASTRUM_PRIVATE_KEY is empty or invalid for Fernet"
    return _request("POST", "/source/v2/applications/new", json_payload={"encrypted_application": token})


def astrum_create_payin(
    *,
    foreign_id: str,
    amount: Decimal | float | str,
    method_type_id: int | None = None,
    method_name_id: int | None = None,
    client_id: str | None = None,
    initials: str | None = None,
    currency: str | None = None,
) -> tuple[bool, dict[str, Any] | str]:
    """POST /source/deal — create KZT pay-in and get card/phone requisite."""
    mt = method_type_id if method_type_id is not None else _method_type_id()
    if mt is None:
        return False, "ASTRUM_METHOD_TYPE_ID is empty — run: python manage.py astrum_probe --methods"
    mn = method_name_id if method_name_id is not None else _method_name_id()
    payload: dict[str, Any] = {
        "foreignId": str(foreign_id),
        "amount": float(amount),
        "methodTypeId": int(mt),
        "methodNameId": int(mn) if mn is not None else None,
        "clientId": (client_id or "").strip() or None,
        "initials": (initials or "").strip() or None,
        "currency": (currency or _currency()).strip().upper() or None,
    }
    token = encrypt_application(payload)
    if not token:
        return False, "ASTRUM_PRIVATE_KEY is empty or invalid for Fernet"
    return _request("POST", "/source/deal", json_payload={"encrypted_application": token})


def astrum_cancel_payin(foreign_id: str) -> tuple[bool, dict[str, Any] | str]:
    """PUT /source/deal/cancel."""
    return _request("PUT", "/source/deal/cancel", json_payload={"foreignId": str(foreign_id)})


def astrum_get_payin_info(foreign_id: str) -> tuple[bool, dict[str, Any] | str]:
    """GET /source/deal/info?foreignId=…"""
    return _request("GET", "/source/deal/info", params={"foreignId": str(foreign_id)})


def _deal_result(create_body: dict | None) -> dict:
    if not isinstance(create_body, dict):
        return {}
    result = create_body.get("result")
    return result if isinstance(result, dict) else {}


def astrum_map_requisite(create_body: dict | None) -> dict:
    """Map Astrum POST /source/deal response → merchant payment_details fields."""
    result = _deal_result(create_body)
    raw = (result.get("requisite") or "").strip() if result else ""
    if not raw and isinstance(create_body, dict):
        raw = str(create_body.get("requisite") or "").strip()
    if not raw:
        return {}

    first = (result.get("firstName") or result.get("first_name") or "").strip()
    mid = (result.get("middleName") or result.get("middle_name") or "").strip()
    last = (result.get("lastName") or result.get("last_name") or "").strip()
    owner = " ".join(p for p in (first, mid, last) if p).strip()
    bank = (result.get("methodName") or result.get("method_name") or "").strip()

    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) >= 16:
        out = {"card_number": digits[:16]}
    elif raw.startswith("+") or (digits and len(digits) <= 12):
        out = {"phone": raw if raw.startswith("+") else f"+{digits}"}
    else:
        out = {"card_number": raw}

    if owner:
        out["owner"] = owner
    if bank:
        out["bank"] = bank
    return out


def astrum_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import AstrumPayInSession
    from payments.psp_payin import requisite_payload_has_fields

    s = AstrumPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = astrum_map_requisite(s.create_response or {})
    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = astrum_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def astrum_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import AstrumPayInSession

    try:
        s = AstrumPayInSession.objects.get(pay_in=pay_in)
    except AstrumPayInSession.DoesNotExist:
        return
    ext = s.external_id or str(pay_in.id)
    ok, data = astrum_cancel_payin(ext)
    if not ok:
        logger.warning("Astrum cancel failed PayIn=%s detail=%s", pay_in.id, data)


def _client_id_for_payin(pay_in: Any) -> str | None:
    if getattr(pay_in, "client_id", None) and getattr(pay_in, "client", None):
        return str(pay_in.client.client_id)
    return None


def _initials_for_payin(pay_in: Any) -> str | None:
    if getattr(pay_in, "client_id", None) and getattr(pay_in, "client", None):
        name = (getattr(pay_in.client, "name", None) or "").strip()
        if name:
            return name
    return None


def try_attach_astrum_session(pay_in: Any) -> bool | None:
    """Astrum POST /source/deal for virtual astrum_kzt group."""
    from payments.models import AstrumPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_astrum_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    external_id = str(pay_in.id)
    currency_sym = (pay_in.currency.symbol or "KZT").strip().upper() if pay_in.currency else "KZT"

    session, _ = AstrumPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": external_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = external_id
    session.save(update_fields=["external_id", "updated_at"])

    ok, data = astrum_create_payin(
        foreign_id=external_id,
        amount=pay_in.amount,
        client_id=_client_id_for_payin(pay_in),
        initials=_initials_for_payin(pay_in),
        currency=currency_sym,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Astrum create pay-in failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    result = _deal_result(session.create_response)
    session.provider_deal_id = str(result.get("innerId") or result.get("inner_id") or "")
    session.save(update_fields=["create_response", "provider_deal_id", "updated_at"])

    req = astrum_map_requisite(session.create_response)
    if not req:
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.provider_deal_id = ""
        session.save(update_fields=["create_response", "provider_deal_id", "updated_at"])
        astrum_cancel_payin(external_id)
        logger.error("Astrum: no requisite PayIn=%s", pay_in.id)
        return False
    return True


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _webhook_payload(body: dict) -> dict:
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("result"), dict) and "status" not in body:
        return body["result"]
    return body


def astrum_payout_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (ignore intermediate)."""
    status = _norm_status(_webhook_payload(body).get("status"))
    if status in _PAYOUT_SUCCESS:
        return "success"
    if status in _PAYOUT_FAIL:
        return "fail"
    return None


def astrum_payin_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (ignore intermediate)."""
    status = _norm_status(_webhook_payload(body).get("status"))
    if status in _PAYIN_SUCCESS:
        return "success"
    if status in _PAYIN_FAIL:
        return "fail"
    return None


def astrum_webhook_foreign_id(body: dict) -> str | None:
    if not isinstance(body, dict):
        return None
    for key in ("foreign_id", "foreignId"):
        val = body.get(key)
        if val:
            return str(val)
    result = body.get("result")
    if isinstance(result, dict):
        for key in ("foreign_id", "foreignId"):
            val = result.get(key)
            if val:
                return str(val)
    return None


def astrum_webhook_inner_id(body: dict) -> str | None:
    if not isinstance(body, dict):
        return None
    for key in ("inner_id", "innerId"):
        val = body.get(key)
        if val:
            return str(val)
    result = body.get("result")
    if isinstance(result, dict):
        for key in ("inner_id", "innerId"):
            val = result.get(key)
            if val:
                return str(val)
    return None


def _requisite_from_payout(pay_out: Any) -> str | None:
    details = pay_out.details if isinstance(pay_out.details, dict) else {}
    for key in ("card_number", "requisite", "iban", "phone", "account_number", "deposit_number"):
        raw = details.get(key)
        if raw is None:
            continue
        value = str(raw).strip().replace(" ", "")
        if value:
            return value
    return None


def _client_initials_from_payout(pay_out: Any) -> str:
    details = pay_out.details if isinstance(pay_out.details, dict) else {}
    for key in ("clientInitials", "client_initials", "owner", "name", "fio"):
        raw = (details.get(key) or "").strip()
        if raw:
            return raw
    first = (details.get("firstName") or details.get("first_name") or "").strip()
    last = (details.get("lastName") or details.get("last_name") or "").strip()
    mid = (details.get("middleName") or details.get("middle_name") or "").strip()
    joined = " ".join(p for p in (first, mid, last) if p).strip()
    if joined:
        return joined
    if pay_out.client_id and getattr(pay_out, "client", None):
        name = (getattr(pay_out.client, "name", None) or "").strip()
        if name:
            return name
    return "Client"


def try_create_astrum_payout(pay_out: Any, *, client_ip: str | None = None) -> bool | None:
    """Create Astrum withdrawal after OutOrder for astrum_kzt trader.

    Returns:
      None — not our trader / skip
      True — provider accepted
      False — create failed (caller should decline OutOrder)
    """
    del client_ip  # Astrum create payload has no client IP field
    from payments.models import AstrumPayOutSession

    order = getattr(pay_out, "order", None)
    if order is None or order.payment_details is None:
        return None
    trader = order.payment_details.group.trader
    if not is_astrum_trader(trader):
        return None

    requisite = _requisite_from_payout(pay_out)
    if not requisite:
        logger.error("Astrum payout: missing requisite PayOut=%s", pay_out.id)
        return False

    external_id = str(pay_out.id)
    session, _ = AstrumPayOutSession.objects.get_or_create(
        pay_out=pay_out,
        defaults={"external_id": external_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = external_id
    session.save(update_fields=["external_id", "updated_at"])

    ok, data = astrum_create_payout(
        foreign_id=external_id,
        amount=pay_out.amount,
        requisite=requisite,
        client_initials=_client_initials_from_payout(pay_out),
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Astrum create payout failed PayOut=%s: %s", pay_out.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    result = session.create_response.get("result") if isinstance(session.create_response, dict) else None
    inner_id = ""
    if isinstance(result, dict):
        inner_id = str(result.get("innerId") or result.get("inner_id") or "")
    session.provider_application_id = inner_id
    session.save(update_fields=["create_response", "provider_application_id", "updated_at"])
    return True
