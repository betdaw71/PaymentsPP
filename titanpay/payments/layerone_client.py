"""HTTP client for Layer-1 PSP (layer-1.io, Aggrepay API v2, method c2ckz)."""
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

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def layerone_trader_username() -> str:
    return getattr(settings, "LAYERONE_TRADER_USERNAME", "layerone1")


def is_layerone_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == layerone_trader_username()


def _parse_method_map() -> dict[str, str]:
    raw = getattr(settings, "LAYERONE_PAYIN_METHOD_MAP", None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    try:
        data = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("LAYERONE_PAYIN_METHOD_MAP is not valid JSON")
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def layerone_payin_method_for(payment_system_name: str | None) -> str:
    """Layer-1 method: KZT — c2ckz."""
    ps_name = (payment_system_name or "").strip()
    mapped = _parse_method_map().get(ps_name)
    if mapped:
        return mapped.strip()
    return (getattr(settings, "LAYERONE_PAYIN_METHOD", None) or "c2ckz").strip()


def layerone_callback_url() -> str:
    explicit = (getattr(settings, "LAYERONE_CALLBACK_URL", None) or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/layerone/"


def _api_key() -> str:
    return (getattr(settings, "LAYERONE_API_KEY", None) or "").strip()


def _merchant_id() -> str:
    return (getattr(settings, "LAYERONE_MERCHANT_ID", None) or "").strip()


def _secret_key() -> str:
    return (getattr(settings, "LAYERONE_SECRET_KEY", None) or "").strip()


def _api_base() -> str:
    return (getattr(settings, "LAYERONE_API_BASE", "https://layer-1.io") or "").rstrip("/")


def _canonical_body(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _sign_body(body: str) -> str:
    return hmac.new(_secret_key().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def _headers(body: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_api_key()}",
        "Signature": _sign_body(body),
        "User-Agent": _BROWSER_UA,
    }


def _normalize_received_signature(signature: str | None) -> str | None:
    sig = (signature or "").strip()
    if not sig:
        return None
    if sig.lower().startswith("sha256="):
        sig = sig.split("=", 1)[1].strip()
    return sig.lower() or None


def _webhook_signing_keys() -> list[str]:
    keys: list[str] = []
    for val in (_secret_key(), _api_key()):
        if val and val not in keys:
            keys.append(val)
    extra = (getattr(settings, "LAYERONE_WEBHOOK_SIGNING_KEYS", None) or "").strip()
    for part in extra.split(","):
        part = part.strip()
        if part and part not in keys:
            keys.append(part)
    return keys


def _webhook_body_candidates(raw_body: bytes) -> list[bytes]:
    candidates = [raw_body]
    try:
        text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        return candidates
    if text:
        candidates.append(text.encode("utf-8"))
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                canonical = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
                canonical_bytes = canonical.encode("utf-8")
                if canonical_bytes not in candidates:
                    candidates.append(canonical_bytes)
        except (json.JSONDecodeError, TypeError):
            pass
    return candidates


def _hmac_sha256_hex(key: str, message: bytes) -> str:
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest().lower()


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    sig = _normalize_received_signature(signature)
    if not sig:
        return False
    if getattr(settings, "LAYERONE_WEBHOOK_SKIP_VERIFY", False):
        logger.warning("LayerOne webhook: LAYERONE_WEBHOOK_SKIP_VERIFY is enabled")
        return True
    keys = _webhook_signing_keys()
    if not keys:
        return False
    for key in keys:
        for message in _webhook_body_candidates(raw_body):
            if hmac.compare_digest(sig, _hmac_sha256_hex(key, message)):
                return True
    return False


def _request(
    method: str,
    path: str,
    *,
    json_payload: dict | None = None,
    timeout: int = 60,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    if not _api_key():
        return False, "LAYERONE_API_KEY is empty"
    if not _merchant_id():
        return False, "LAYERONE_MERCHANT_ID is empty"
    if not _secret_key():
        return False, "LAYERONE_SECRET_KEY is empty"
    base = _api_base()
    if not base:
        return False, "LAYERONE_API_BASE is empty"
    payload = json_payload or {}
    body = _canonical_body(payload)
    url = f"{base}/{path.lstrip('/')}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.LAYERONE_OUT_REQUEST,
        body=payload,
        http_method=method,
        url=url,
        note="LayerOne API",
    )
    try:
        if method.upper() == "GET":
            r = requests.request(method, url, headers=_headers(body), timeout=timeout)
        else:
            r = requests.request(method, url, data=body.encode("utf-8"), headers=_headers(body), timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("LayerOne %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.LAYERONE_OUT_RESPONSE,
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
        direction=Direction.LAYERONE_OUT_RESPONSE,
        body=resp_body,
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="LayerOne API",
    )
    if not isinstance(resp_body, dict):
        return False, {"error": str(resp_body)}
    if not r.ok or resp_body.get("status") is False:
        return False, resp_body
    return True, resp_body


def layerone_get_methods(*, currency: str = "KZT") -> tuple[bool, dict[str, Any] | str]:
    cur = (currency or "KZT").strip().upper()
    return _request("GET", f"/api/v2/methods?currency={cur}", json_payload={}, pay_in=None)


def layerone_create_payment(
    *,
    amount: Decimal,
    order_id: str,
    currency: str,
    callback_url: str | None = None,
    payer_user_id: str | None = None,
    payer_ip: str | None = None,
    payer_user_agent: str | None = None,
    method: str | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    payin_method = (method or getattr(settings, "LAYERONE_PAYIN_METHOD", None) or "c2ckz").strip()
    payer: dict[str, Any] = {
        "userId": payer_user_id or order_id,
        "userIp": payer_ip or getattr(settings, "LAYERONE_DEFAULT_PAYER_IP", "127.0.0.1"),
    }
    if payer_user_agent:
        payer["userAgent"] = payer_user_agent
    payload: dict[str, Any] = {
        "orderId": order_id,
        "merchantId": _merchant_id(),
        "amount": str(int(amount)) if amount == amount.to_integral_value() else str(amount),
        "currency": currency.upper(),
        "method": payin_method,
        "callbackUri": callback_url or layerone_callback_url(),
        "payer": payer,
    }
    asset_or_bank = (getattr(settings, "LAYERONE_ASSET_OR_BANK", None) or "").strip()
    if asset_or_bank:
        payload["assetOrBank"] = asset_or_bank
    return _request("POST", "/api/v2/payments", json_payload=payload, pay_in=pay_in)


def _norm_state(raw: str | None) -> str:
    return (raw or "").strip().lower()


def layerone_webhook_ids(body: dict | None) -> tuple[str, str]:
    from payments.aggrepay_webhook import webhook_ids

    return webhook_ids(body)


def layerone_webhook_state(body: dict | None) -> str:
    from payments.aggrepay_webhook import webhook_state

    return webhook_state(body)


def resolve_layerone_webhook_session(
    *,
    order_id: str | None,
    payment_id: str | None,
):
    from payments.models import LayeronePayInSession, PayIn

    oid = (order_id or "").strip()
    pid = (payment_id or "").strip()

    if oid:
        session = (
            LayeronePayInSession.objects.filter(external_id=oid)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session is not None:
            return session

    if pid:
        session = (
            LayeronePayInSession.objects.filter(provider_payment_id=pid)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session is not None:
            return session

    if not oid:
        return None

    pay_in = PayIn.objects.filter(pk=oid).select_related("order__payment_details__group__trader").first()
    if pay_in is None or pay_in.order is None or pay_in.order.payment_details is None:
        return None
    if not is_layerone_trader(pay_in.order.payment_details.group.trader):
        return None

    session, created = LayeronePayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": str(pay_in.id), "create_response": {}, "last_webhook_payload": {}},
    )
    updates: list[str] = []
    if str(session.external_id) != str(pay_in.id):
        session.external_id = str(pay_in.id)
        updates.append("external_id")
    if pid and not session.provider_payment_id:
        session.provider_payment_id = pid
        updates.append("provider_payment_id")
    if updates:
        updates.append("updated_at")
        session.save(update_fields=updates)
    if created:
        logger.info("LayerOne webhook: recovered session for PayIn=%s orderId=%s", pay_in.id, oid)
    return session


def layerone_webhook_outcome(body: dict) -> str | None:
    from payments.aggrepay_webhook import webhook_outcome

    return webhook_outcome(body)


def layerone_is_webhook_body(body: dict | None) -> bool:
    if not isinstance(body, dict):
        return False
    from payments.aggrepay_webhook import webhook_ids, webhook_state

    state = webhook_state(body)
    order_id, payment_id = webhook_ids(body)
    return bool(state and (order_id or payment_id))


def layerone_success_webhook_allows_completed_recalc(body: dict | None) -> bool:
    if not layerone_is_webhook_body(body):
        return False
    return layerone_webhook_outcome(body) == "success"


def _layerone_result(create_body: dict) -> dict:
    if not isinstance(create_body, dict):
        return {}
    result = create_body.get("result") if isinstance(create_body.get("result"), dict) else {}
    data = create_body.get("data") if isinstance(create_body.get("data"), dict) else {}
    nested = create_body.get("requisite") if isinstance(create_body.get("requisite"), dict) else {}
    inner = result.get("requisite") if isinstance(result.get("requisite"), dict) else {}
    merged: dict = {}
    for part in (create_body, data, nested, result, inner):
        if isinstance(part, dict):
            merged.update({k: v for k, v in part.items() if v not in (None, "")})
    return merged


def layerone_map_requisite(create_body: dict) -> dict:
    result = _layerone_result(create_body)
    owner = result.get("recipient") or result.get("cardHolder") or result.get("holder_name") or ""
    bank = result.get("bankName") or result.get("bank") or ""
    address = str(
        result.get("address")
        or result.get("cardNumber")
        or result.get("card_number")
        or result.get("pan")
        or result.get("phone_number")
        or result.get("phone")
        or ""
    ).strip()
    url = ""
    for key in ("url", "paymentUrl", "payment_url", "widget_url", "payment_form_url"):
        raw = str(result.get(key) or "").strip()
        if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
            url = raw
            break
    if address:
        digits = "".join(c for c in address if c.isdigit())
        if len(digits) >= 16:
            return {"card_number": digits[:16], "owner": owner, "bank": bank}
        if address.startswith("+") or (digits and len(digits) <= 12):
            return {
                "phone": address if address.startswith("+") else f"+{digits}",
                "owner": owner,
                "bank": bank,
            }
        return {"card_number": address, "owner": owner, "bank": bank}
    if url:
        return {"payment_form_url": url, "owner": owner, "bank": bank}
    return {}


def layerone_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import LayeronePayInSession
    from payments.psp_payin import requisite_payload_has_fields

    s = LayeronePayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = layerone_map_requisite(s.create_response or {})
    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = layerone_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def try_attach_layerone_session(pay_in: Any) -> bool | None:
    from payments.models import LayeronePayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_layerone_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    currency_sym = (pay_in.currency.symbol or "KZT").strip().upper() if pay_in.currency else "KZT"
    external_id = str(pay_in.id)

    session, _ = LayeronePayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": external_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = external_id
    session.save(update_fields=["external_id", "updated_at"])

    client = getattr(pay_in, "client", None)
    payer_user_id = str(pay_in.id)
    if client is not None and getattr(client, "client_id", None):
        payer_user_id = str(client.client_id)

    payer_ip = None
    payer_ua = None
    if client is not None:
        device = client.devices.first()
        if device is not None:
            payer_ip = (device.ip_address or "").strip() or None
            payer_ua = (device.user_agent or "").strip() or None

    ok, data = layerone_create_payment(
        amount=pay_in.amount,
        order_id=external_id,
        currency=currency_sym,
        payer_user_id=payer_user_id,
        payer_ip=payer_ip,
        payer_user_agent=payer_ua,
        method=layerone_payin_method_for(
            pay_in.payment_system.name if pay_in.payment_system else None
        ),
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("LayerOne create payment failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    result = (session.create_response or {}).get("result") or {}
    session.provider_payment_id = str(result.get("id") or "")
    session.save(update_fields=["create_response", "provider_payment_id", "updated_at"])

    req = layerone_map_requisite(session.create_response)
    state = _norm_state(result.get("state"))
    if not req and state not in ("created",):
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.provider_payment_id = ""
        session.save(update_fields=["create_response", "provider_payment_id", "updated_at"])
        logger.error("LayerOne: no requisite PayIn=%s state=%s", pay_in.id, state)
        return False
    return True if req else False


def layerone_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import LayeronePayInSession

    try:
        s = LayeronePayInSession.objects.get(pay_in=pay_in)
    except LayeronePayInSession.DoesNotExist:
        return
    if s.provider_payment_id:
        logger.info(
            "LayerOne cancel skipped PayIn=%s provider_payment_id=%s (no cancel API)",
            pay_in.id,
            s.provider_payment_id,
        )
