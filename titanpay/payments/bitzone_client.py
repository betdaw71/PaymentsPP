"""HTTP client for Bitzone PSP (api.bitzone.space, pay-in trading API)."""
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


def bitzone_trader_username() -> str:
    return getattr(settings, "BITZONE_TRADER_USERNAME", "bitzone1")


def is_bitzone_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == bitzone_trader_username()


def bitzone_callback_url() -> str:
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/bitzone/"


def _api_key() -> str:
    return (getattr(settings, "BITZONE_API_KEY", None) or "").strip()


def _api_base() -> str:
    return (getattr(settings, "BITZONE_API_BASE", "https://api.bitzone.space") or "").rstrip("/")


def _canonical_body(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _sign_body(body: str) -> str:
    return hmac.new(_api_key().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def _signing_keys_for_webhook() -> list[str]:
    keys: list[str] = []
    for env_name in ("BITZONE_WEBHOOK_SECRET", "BITZONE_API_KEY"):
        val = (getattr(settings, env_name, None) or "").strip()
        if val and val not in keys:
            keys.append(val)
    extra = (getattr(settings, "BITZONE_WEBHOOK_SIGNING_KEYS", None) or "").strip()
    if extra:
        for part in extra.split(","):
            part = part.strip()
            if part and part not in keys:
                keys.append(part)
    return keys


def _webhook_body_candidates(raw_body: bytes) -> list[bytes]:
    if not raw_body:
        return []
    out: list[bytes] = []
    seen: set[bytes] = set()

    def add(b: bytes) -> None:
        if b and b not in seen:
            seen.add(b)
            out.append(b)

    add(raw_body)
    if raw_body.startswith(b"\xef\xbb\xbf"):
        add(raw_body[3:])
    add(raw_body.rstrip(b" \t\r\n"))
    try:
        text = raw_body.decode("utf-8")
        add(text.encode("utf-8"))
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            for sort_keys in (False, True):
                canon = json.dumps(
                    parsed, separators=(",", ":"), ensure_ascii=False, sort_keys=sort_keys
                )
                add(canon.encode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    return out


def _normalize_received_signature(signature: str | None) -> str | None:
    if not signature:
        return None
    sig = signature.strip()
    if sig.lower().startswith("sha256="):
        sig = sig.split("=", 1)[1].strip()
    return sig.lower() or None


def _hmac_sha256_hex(key: str, message: bytes) -> str:
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest().lower()


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    sig = _normalize_received_signature(signature)
    if not sig:
        return False
    if getattr(settings, "BITZONE_WEBHOOK_SKIP_VERIFY", False):
        logger.warning("Bitzone webhook: BITZONE_WEBHOOK_SKIP_VERIFY is enabled")
        return True

    keys = _signing_keys_for_webhook()
    if not keys:
        return False

    messages = _webhook_body_candidates(raw_body)
    for key in keys:
        for message in messages:
            expected_hex = _hmac_sha256_hex(key, message)
            if hmac.compare_digest(sig, expected_hex):
                return True
            # Некоторые провайдеры отдают base64 вместо hex
            try:
                import base64

                expected_b64 = base64.b64encode(
                    hmac.new(key.encode("utf-8"), message, hashlib.sha256).digest()
                ).decode("ascii")
                if hmac.compare_digest(sig, expected_b64.lower()):
                    return True
            except Exception:  # noqa: BLE001
                pass
    return False


def _headers(body: str, *, sign: bool) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-api-key": _api_key(),
    }
    if sign:
        headers["x-signature"] = _sign_body(body)
    return headers


def _should_sign_outbound() -> bool:
    return getattr(settings, "BITZONE_SIGN_OUTBOUND", True)


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
        return False, "BITZONE_API_KEY is empty"
    base = _api_base()
    if not base:
        return False, "BITZONE_API_BASE is empty"

    payload = json_payload or {}
    body = _canonical_body(payload)
    url = f"{base}/{path.lstrip('/')}"
    sign = _should_sign_outbound() and method.upper() in ("POST", "PUT", "PATCH")

    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.BITZONE_OUT_REQUEST,
        body=payload,
        http_method=method,
        url=url,
        note="Bitzone API",
    )
    try:
        r = requests.request(
            method,
            url,
            data=body.encode("utf-8"),
            headers=_headers(body, sign=sign),
            timeout=timeout,
        )
    except requests.RequestException as exc:
        logger.exception("Bitzone %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.BITZONE_OUT_RESPONSE,
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
        direction=Direction.BITZONE_OUT_RESPONSE,
        body=resp_body,
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="Bitzone API",
    )
    if not isinstance(resp_body, dict):
        return False, {"error": str(resp_body)}
    if not r.ok:
        return False, resp_body
    return True, resp_body


def bitzone_payin_method_for(payment_system_name: str, currency_symbol: str) -> str:
    raw = getattr(settings, "BITZONE_METHOD_MAP", None)
    if isinstance(raw, dict):
        if payment_system_name in raw:
            return str(raw[payment_system_name])
        cur = (currency_symbol or "").upper()
        if cur in raw:
            return str(raw[cur])
    default = (getattr(settings, "BITZONE_PAYIN_METHOD", None) or "card").strip()
    return default


def bitzone_create_pay_in(
    *,
    fiat_amount: Decimal,
    fiat_currency: str,
    external_transaction_id: str,
    method: str | None = None,
    bank: str | None = None,
    payer_user_id: str | None = None,
    payer_ip: str | None = None,
    payer_user_agent: str | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    """POST /payment/trading/pay-in — см. https://developers.bitzone.space/docs/pay-in/"""
    cur = (fiat_currency or "KZT").strip().upper()
    amt = fiat_amount
    if amt == amt.to_integral_value():
        fiat_field: int | str = int(amt)
    else:
        fiat_field = str(amt.quantize(Decimal("0.01")))

    payload: dict[str, Any] = {
        "fiatAmount": fiat_field,
        "fiatCurrency": cur,
        "method": (method or "card").strip(),
        "extra": {
            "externalTransactionId": external_transaction_id,
            "payerInfo": {
                "ip": payer_ip or getattr(settings, "BITZONE_DEFAULT_PAYER_IP", "127.0.0.1"),
                "userId": payer_user_id or external_transaction_id,
            },
        },
    }
    if payer_user_agent:
        payload["extra"]["payerInfo"]["userAgent"] = payer_user_agent
    bank_val = (bank or getattr(settings, "BITZONE_BANK", None) or "").strip()
    if bank_val:
        payload["bank"] = bank_val
    payload["callbackUrl"] = bitzone_callback_url()

    return _request("POST", "/payment/trading/pay-in", json_payload=payload, pay_in=pay_in)


def bitzone_cancel_pay_in(provider_id: str, *, pay_in=None) -> tuple[bool, dict[str, Any] | str]:
    if not provider_id:
        return False, "empty provider id"
    return _request("POST", f"/payment/trading/pay-in/{provider_id}/cancel", json_payload={}, pay_in=pay_in)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def bitzone_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (intermediate)."""
    status = _norm_status(body.get("status"))
    if status == "closed":
        return "success"
    if status in ("canceled", "cancelled"):
        return "fail"
    return None


def bitzone_map_requisite(create_body: dict) -> dict:
    """Маппинг requisite из ответа Bitzone в payment_details для мерчанта."""
    if not isinstance(create_body, dict):
        return {}
    req = create_body.get("requisite")
    if not isinstance(req, dict):
        return {}
    owner = req.get("ownerName") or ""
    bank = req.get("bank") or create_body.get("bank") or ""
    sbp = (req.get("sbpNumber") or "").strip()
    if sbp:
        phone = sbp if sbp.startswith("+") else f"+{''.join(c for c in sbp if c.isdigit())}"
        return {"phone": phone, "owner": owner, "bank": bank}
    raw_req = (req.get("requisites") or "").strip()
    if not raw_req:
        return {}
    digits = "".join(c for c in raw_req if c.isdigit())
    if len(digits) >= 16:
        return {"card_number": digits[:16], "owner": owner, "bank": bank}
    if raw_req.startswith("+") or (digits and len(digits) <= 12):
        return {"phone": raw_req if raw_req.startswith("+") else f"+{digits}", "owner": owner, "bank": bank}
    return {"card_number": raw_req, "owner": owner, "bank": bank}


def bitzone_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import BitzonePayInSession

    s = BitzonePayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = bitzone_map_requisite(s.create_response or {})
    from payments.psp_payin import requisite_payload_has_fields

    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = bitzone_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def bitzone_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import BitzonePayInSession

    try:
        s = BitzonePayInSession.objects.get(pay_in=pay_in)
    except BitzonePayInSession.DoesNotExist:
        return
    if not s.provider_transaction_id:
        return
    ok, data = bitzone_cancel_pay_in(s.provider_transaction_id, pay_in=pay_in)
    if not ok:
        logger.warning(
            "Bitzone cancel failed PayIn=%s provider_id=%s detail=%s",
            pay_in.id,
            s.provider_transaction_id,
            data,
        )


def try_attach_bitzone_session(pay_in: Any) -> bool | None:
    """Bitzone API для виртуальной группы bitzone1."""
    from payments.models import BitzonePayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_bitzone_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    ps_name = pay_in.payment_system.name if pay_in.payment_system else ""
    currency_sym = (pay_in.currency.symbol or "KZT").strip() if pay_in.currency else "KZT"
    external_id = str(pay_in.id)

    session, _ = BitzonePayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": external_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = external_id
    session.save(update_fields=["external_id", "updated_at"])

    method = bitzone_payin_method_for(ps_name, currency_sym)
    payer_user_id = external_id
    if getattr(settings, "BITZONE_PAYER_USER_ID_FROM_CLIENT", False):
        if pay_in.client_id and getattr(pay_in, "client", None):
            payer_user_id = str(pay_in.client.client_id)

    ok, data = bitzone_create_pay_in(
        fiat_amount=pay_in.amount,
        fiat_currency=currency_sym,
        external_transaction_id=external_id,
        method=method,
        payer_user_id=payer_user_id,
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Bitzone create pay-in failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    session.provider_transaction_id = str((session.create_response or {}).get("id") or "")
    session.save(update_fields=["create_response", "provider_transaction_id", "updated_at"])

    req = bitzone_map_requisite(session.create_response)
    tx_status = _norm_status((session.create_response or {}).get("status"))
    if not req:
        pid = session.provider_transaction_id
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.provider_transaction_id = ""
        session.save(update_fields=["create_response", "provider_transaction_id", "updated_at"])
        if pid:
            bitzone_cancel_pay_in(pid, pay_in=pay_in)
        logger.error("Bitzone: no requisite PayIn=%s status=%s", pay_in.id, tx_status)
        return False
    return True
