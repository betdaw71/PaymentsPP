"""HTTP client for Playments PSP (TRY bank transfer H2H pay-in / pay-out)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_DEPOSIT_TERMINAL_FAIL = frozenset(
    {"Fail", "Expired", "Cancelled", "Rejected", "NotPaid", "Chargeback"}
)
_WITHDRAWAL_TERMINAL_FAIL = frozenset({"Fail", "Rejected", "Reversed"})


def playments_trader_username() -> str:
    return getattr(settings, "PLAYMENTS_TRADER_USERNAME", "playments1")


def is_playments_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == playments_trader_username()


def playments_payment_system_name() -> str:
    return getattr(settings, "PLAYMENTS_C2C_NAME", "C2CTRY")


def playments_deposit_callback_url() -> str:
    explicit = (getattr(settings, "PLAYMENTS_DEPOSIT_CALLBACK_URL", None) or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/playments/deposit/"


def playments_withdrawal_callback_url() -> str:
    explicit = (getattr(settings, "PLAYMENTS_WITHDRAWAL_CALLBACK_URL", None) or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/playments/withdrawal/"


def _merchant_group_id() -> str:
    return (getattr(settings, "PLAYMENTS_MERCHANT_GROUP_ID", None) or "").strip()


def _merchant_id() -> str:
    return (getattr(settings, "PLAYMENTS_MERCHANT_ID", None) or "").strip()


def _secret_key() -> str:
    return (getattr(settings, "PLAYMENTS_SECRET_KEY", None) or "").strip()


def _webhook_secret_key() -> str:
    return (
        (getattr(settings, "PLAYMENTS_WEBHOOK_SECRET", None) or "").strip()
        or _secret_key()
    )


def _api_base() -> str:
    explicit = (getattr(settings, "PLAYMENTS_API_BASE", None) or "").strip().rstrip("/")
    if explicit:
        return explicit
    if "_sbx_" in _merchant_group_id().lower() or _merchant_group_id().lower().startswith("mgr_sbx"):
        return "https://api.sbx.playments.world"
    return "https://api.playments.world"


def _canonical_body(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _sign_api_request(http_method: str, path_and_query: str, body: str) -> str:
    to_encrypt = f"{http_method.upper()}{path_and_query}{body}"
    return hmac.new(_secret_key().encode("utf-8"), to_encrypt.encode("utf-8"), hashlib.sha256).hexdigest()


def _sign_webhook_body(raw_body: bytes) -> str:
    return hmac.new(_webhook_secret_key().encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _use_raw_secret() -> bool:
    """
    SBX: Playments docs allow `Request-Signature: {MerchantGroupId}:{SecretKey}` without HMAC.
    Auto-enabled when GROUP_ID contains `_sbx_`; override via PLAYMENTS_USE_RAW_SECRET.
    """
    explicit = getattr(settings, "PLAYMENTS_USE_RAW_SECRET", None)
    if explicit is not None:
        return bool(explicit)
    group_id = _merchant_group_id().lower()
    return "_sbx_" in group_id or group_id.startswith("mgr_sbx")


def _request_signature(http_method: str, path_and_query: str, body: str) -> str:
    group_id = _merchant_group_id()
    if _use_raw_secret():
        return f"{group_id}:{_secret_key()}"
    signature = _sign_api_request(http_method, path_and_query, body)
    return f"{group_id}:{signature}"


def verify_webhook_signature(raw_body: bytes, header_value: str | None) -> bool:
    webhook_secret = _webhook_secret_key()
    group_id = _merchant_group_id()
    if not webhook_secret or not group_id or not header_value:
        return False
    parts = header_value.strip().split(":", 1)
    if len(parts) != 2 or parts[0].strip() != group_id:
        return False
    received = parts[1].strip()
    expected = _sign_webhook_body(raw_body)
    if hmac.compare_digest(received, expected):
        return True
    # SBX иногда шлёт webhook secret как есть (аналог raw API key на sandbox).
    if _use_raw_secret() and hmac.compare_digest(received, webhook_secret):
        return True
    logger.warning(
        "Playments webhook signature mismatch group=%s body_len=%s (check PLAYMENTS_WEBHOOK_SECRET)",
        group_id,
        len(raw_body),
    )
    return False


def _request(
    method: str,
    path: str,
    *,
    json_payload: dict | None = None,
    timeout: int = 60,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    if not _merchant_group_id():
        return False, "PLAYMENTS_MERCHANT_GROUP_ID is empty"
    if not _merchant_id():
        return False, "PLAYMENTS_MERCHANT_ID is empty"
    if not _secret_key():
        return False, "PLAYMENTS_SECRET_KEY is empty"
    base = _api_base()
    if not base:
        return False, "PLAYMENTS_API_BASE is empty"

    payload = json_payload or {}
    body = _canonical_body(payload)
    path_and_query = f"/{path.lstrip('/')}"
    url = f"{base}{path_and_query}"

    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.PLAYMENTS_OUT_REQUEST,
        body=payload,
        http_method=method,
        url=url,
        note="Playments API",
    )
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Request-Signature": _request_signature(method, path_and_query, body),
    }
    try:
        r = requests.request(method, url, data=body.encode("utf-8"), headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("Playments %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.PLAYMENTS_OUT_RESPONSE,
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
        direction=Direction.PLAYMENTS_OUT_RESPONSE,
        body=resp_body,
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="Playments API",
    )
    if not isinstance(resp_body, dict):
        return False, {"error": str(resp_body)}
    if not r.ok:
        return False, resp_body
    return True, resp_body


def _split_name(full_name: str | None) -> tuple[str, str]:
    raw = (full_name or "").strip()
    if not raw:
        return "Client", "User"
    parts = raw.split(None, 1)
    if len(parts) == 1:
        return parts[0], "User"
    return parts[0], parts[1]


_TRY_PHONE_RE = re.compile(r"^\+90\d{10}$")


def _normalize_try_phone(raw: str | None) -> str | None:
    """Playments TRY: +90 и ровно 10 цифр; иначе null (не отправлять KZ/RU номера)."""
    phone = (raw or "").strip().replace(" ", "").replace("-", "")
    if not phone:
        return None
    if phone.startswith("90") and not phone.startswith("+"):
        phone = f"+{phone}"
    if phone.startswith("+90") and _TRY_PHONE_RE.match(phone):
        return phone
    return None


def _client_data_from_payin(pay_in: Any) -> dict[str, Any]:
    first, last = "Client", "User"
    email = None
    phone = None
    if pay_in.client_id and getattr(pay_in, "client", None):
        client = pay_in.client
        first, last = _split_name(getattr(client, "name", None))
        email = getattr(client, "email", None) or None
        phone = _normalize_try_phone(getattr(client, "phone", None))
    return {
        "firstName": first,
        "lastName": last,
        "email": email,
        "phoneNumber": phone,
    }


def _client_data_from_payout(pay_out: Any) -> dict[str, Any]:
    details = pay_out.details if isinstance(pay_out.details, dict) else {}
    first = (details.get("firstName") or details.get("first_name") or "").strip()
    last = (details.get("lastName") or details.get("last_name") or "").strip()
    phone = _normalize_try_phone(
        details.get("phoneNumber") or details.get("phone") or details.get("phone_number")
    )
    if not first or not last:
        if pay_out.client_id and getattr(pay_out, "client", None):
            first, last = _split_name(getattr(pay_out.client, "name", None))
            if phone is None:
                phone = _normalize_try_phone(getattr(pay_out.client, "phone", None))
    if not first:
        first = "Client"
    if not last:
        last = "User"
    data: dict[str, Any] = {"firstName": first, "lastName": last}
    if phone is not None:
        data["phoneNumber"] = phone
    return data


def playments_create_deposit(
    *,
    amount: Decimal,
    merchant_transaction_id: str,
    callback_url: str | None = None,
    client_id: str,
    client_ip: str | None = None,
    client_data: dict | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    payload: dict[str, Any] = {
        "merchantId": _merchant_id(),
        "merchantTransactionId": merchant_transaction_id,
        "amount": float(amount),
        "callbackUrl": callback_url or playments_deposit_callback_url(),
        "clientId": client_id,
        "clientIpAddress": client_ip or getattr(settings, "PLAYMENTS_DEFAULT_CLIENT_IP", "127.0.0.1"),
        "clientData": client_data or {"firstName": "Client", "lastName": "User", "email": None, "phoneNumber": None},
        "data": {"firstName": None, "lastName": None},
    }
    return _request("POST", "/api/deposits/try/banktransfer", json_payload=payload, pay_in=pay_in)


def playments_create_withdrawal(
    *,
    amount: Decimal,
    merchant_transaction_id: str,
    iban: str,
    callback_url: str | None = None,
    client_id: str,
    client_ip: str | None = None,
    client_data: dict | None = None,
) -> tuple[bool, dict[str, Any] | str]:
    payload: dict[str, Any] = {
        "merchantId": _merchant_id(),
        "merchantTransactionId": merchant_transaction_id,
        "amount": float(amount),
        "callbackUrl": callback_url or playments_withdrawal_callback_url(),
        "clientId": client_id,
        "clientIpAddress": client_ip or getattr(settings, "PLAYMENTS_DEFAULT_CLIENT_IP", "127.0.0.1"),
        "data": {"iban": iban},
        "clientData": client_data or {"firstName": "Client", "lastName": "User"},
    }
    return _request("POST", "/api/withdrawals/try/banktransfer", json_payload=payload)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip()


def playments_deposit_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (ignore intermediate)."""
    payload = body.get("payload") if isinstance(body, dict) else {}
    if not isinstance(payload, dict):
        return None
    status = _norm_status(payload.get("status"))
    if status == "Success":
        return "success"
    if status in _DEPOSIT_TERMINAL_FAIL:
        return "fail"
    return None


def playments_withdrawal_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (ignore intermediate)."""
    payload = body.get("payload") if isinstance(body, dict) else {}
    if not isinstance(payload, dict):
        return None
    status = _norm_status(payload.get("status"))
    if status in ("Success", "PartialSuccess"):
        return "success"
    if status in _WITHDRAWAL_TERMINAL_FAIL:
        return "fail"
    return None


def playments_webhook_payload(body: dict) -> dict:
    payload = body.get("payload") if isinstance(body, dict) else {}
    return payload if isinstance(payload, dict) else {}


def playments_map_requisite(create_body: dict) -> dict:
    """Map Playments instructions to merchant payment_details."""
    instructions = create_body.get("instructions") if isinstance(create_body, dict) else {}
    if not isinstance(instructions, dict):
        return {}
    bank_account = (instructions.get("bankAccount") or "").strip()
    if not bank_account:
        return {}
    return {
        "deposit_number": bank_account,
        "owner": instructions.get("fullName") or "",
        "bank": instructions.get("bank") or "",
    }


def playments_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import PlaymentsPayInSession

    s = PlaymentsPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    cr = s.create_response or {}
    req = playments_map_requisite(cr)
    from payments.psp_payin import requisite_payload_has_fields

    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = playments_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def try_attach_playments_session(pay_in: Any, *, client_ip: str | None = None) -> bool | None:
    """Playments API for virtual group playments1 (C2CTRY)."""
    from payments.models import PlaymentsPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_playments_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    external_id = str(pay_in.id)
    client_id = external_id
    if pay_in.client_id and getattr(pay_in, "client", None):
        client_id = str(pay_in.client.client_id)

    session, _ = PlaymentsPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": external_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = external_id
    session.save(update_fields=["external_id", "updated_at"])

    ok, data = playments_create_deposit(
        amount=pay_in.amount,
        merchant_transaction_id=external_id,
        client_id=client_id,
        client_ip=client_ip,
        client_data=_client_data_from_payin(pay_in),
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Playments create deposit failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    session.provider_deposit_id = str((session.create_response or {}).get("depositId") or "")
    session.save(update_fields=["create_response", "provider_deposit_id", "updated_at"])

    req = playments_map_requisite(session.create_response)
    if not req:
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.provider_deposit_id = ""
        session.save(update_fields=["create_response", "provider_deposit_id", "updated_at"])
        logger.error("Playments: no requisite PayIn=%s", pay_in.id)
        return False
    return True


def try_create_playments_payout(pay_out: Any, *, client_ip: str | None = None) -> bool | None:
    """Create Playments withdrawal after OutOrder for playments1 trader."""
    from payments.models import PlaymentsPayOutSession

    order = getattr(pay_out, "order", None)
    if order is None or order.payment_details is None:
        return None
    trader = order.payment_details.group.trader
    if not is_playments_trader(trader):
        return None

    details = pay_out.details if isinstance(pay_out.details, dict) else {}
    iban = (details.get("iban") or "").strip()
    if not iban:
        logger.error("Playments payout: missing iban PayOut=%s", pay_out.id)
        return False

    external_id = str(pay_out.id)
    client_id = external_id
    if pay_out.client_id and getattr(pay_out, "client", None):
        client_id = str(pay_out.client.client_id)

    session, _ = PlaymentsPayOutSession.objects.get_or_create(
        pay_out=pay_out,
        defaults={"external_id": external_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = external_id
    session.save(update_fields=["external_id", "updated_at"])

    ok, data = playments_create_withdrawal(
        amount=pay_out.amount,
        merchant_transaction_id=external_id,
        iban=iban,
        client_id=client_id,
        client_ip=client_ip,
        client_data=_client_data_from_payout(pay_out),
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Playments create withdrawal failed PayOut=%s: %s", pay_out.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    session.provider_withdrawal_id = str((session.create_response or {}).get("withdrawalId") or "")
    session.save(update_fields=["create_response", "provider_withdrawal_id", "updated_at"])
    return True


def playments_cancel_if_linked(pay_in: Any) -> None:
    """Playments does not document pay-in cancel — no-op with log."""
    from payments.models import PlaymentsPayInSession

    try:
        s = PlaymentsPayInSession.objects.get(pay_in=pay_in)
    except PlaymentsPayInSession.DoesNotExist:
        return
    if s.provider_deposit_id:
        logger.info(
            "Playments cancel skipped PayIn=%s provider_deposit_id=%s (no cancel API)",
            pay_in.id,
            s.provider_deposit_id,
        )
