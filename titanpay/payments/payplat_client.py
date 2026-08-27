"""HTTP client for PayPlat PSP (https://payplat.su, POST /v1/api/deals)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_REQUISITE_TYPES_NEED_CONTRAGENT = frozenset(
    {
        "qrnspk",
        "qrnspk_ultra",
        "qrdirect",
        "c2c_ab",
        "p2p_tran",
        "c2c_tran",
    }
)


def payplat_trader_username() -> str:
    return getattr(settings, "PAYPLAT_TRADER_USERNAME", "payplat1")


def is_payplat_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == payplat_trader_username()


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


def payplat_requisite_type_for(payment_system_name: str | None) -> str:
    ps_name = (payment_system_name or "").strip()
    mapped = _parse_json_map("PAYPLAT_REQUISITE_TYPE_MAP").get(ps_name)
    if mapped:
        return mapped.strip().lower()
    default = (getattr(settings, "PAYPLAT_REQUISITE_TYPE", None) or "c2c_ab").strip().lower()
    return default or "c2c_ab"


def payplat_bank_for(payment_system_name: str | None) -> str | None:
    ps_name = (payment_system_name or "").strip()
    mapped = _parse_json_map("PAYPLAT_BANK_MAP").get(ps_name)
    if mapped:
        val = mapped.strip()
        return val if val.lower() not in ("null", "none", "") else None
    default = (getattr(settings, "PAYPLAT_BANK", None) or "").strip()
    return default or None


def payplat_tariff() -> str:
    return (getattr(settings, "PAYPLAT_TARIFF", None) or "PRIMARY").strip().upper() or "PRIMARY"


def payplat_callback_url() -> str:
    explicit = (getattr(settings, "PAYPLAT_CALLBACK_URL", None) or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/payplat/"


def _shop_id() -> int:
    raw = getattr(settings, "PAYPLAT_SHOP_ID", None)
    if raw in (None, ""):
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _secret_key() -> str:
    explicit = (getattr(settings, "PAYPLAT_SECRET_KEY", None) or "").strip()
    if explicit:
        return explicit
    shop_id = _shop_id()
    return str(shop_id) if shop_id else ""


def _api_base() -> str:
    default = "https://payplat.su/test/api"
    return (getattr(settings, "PAYPLAT_API_BASE", default) or default).rstrip("/")


def _canonical_body(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _format_amount(amount: Decimal) -> int | float:
    d = Decimal(str(amount)).quantize(Decimal("0.01"))
    if d == d.to_integral_value():
        return int(d)
    return float(d)


def _sign(secret_key: str, body: str, timestamp: str) -> str:
    data = secret_key + body + timestamp
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _headers(*, body: str, timestamp: str | None = None) -> dict[str, str]:
    ts = timestamp or str(int(time.time() * 1000))
    shop_id = _shop_id()
    secret = _secret_key()
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {shop_id}",
        "X-Signature": _sign(secret, body, ts),
        "X-Timestamp": ts,
    }


def _webhook_body_candidates(raw_body: bytes) -> list[str]:
    candidates: list[str] = []
    try:
        text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        return candidates
    if text:
        candidates.append(text)
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                canonical = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
                if canonical not in candidates:
                    candidates.append(canonical)
        except (json.JSONDecodeError, TypeError):
            pass
    return candidates


def verify_webhook_signature(
    raw_body: bytes,
    *,
    signature: str | None,
    timestamp: str | None,
    authorization: str | None = None,
) -> bool:
    if getattr(settings, "PAYPLAT_WEBHOOK_SKIP_VERIFY", False):
        logger.warning("PayPlat webhook: PAYPLAT_WEBHOOK_SKIP_VERIFY is enabled")
        return True

    sig = (signature or "").strip().lower()
    ts = (timestamp or "").strip()
    if not sig or not ts:
        return False

    expected_shop = _shop_id()
    if expected_shop:
        auth = (authorization or "").strip()
        if auth:
            bearer = auth.split(None, 1)[-1].strip() if auth.lower().startswith("bearer ") else auth
            try:
                if int(bearer) != expected_shop:
                    return False
            except (TypeError, ValueError):
                return False

    secret = _secret_key()
    if not secret:
        return False

    now_ms = int(time.time() * 1000)
    try:
        req_ms = int(ts)
    except (TypeError, ValueError):
        return False
    if abs(now_ms - req_ms) > 5 * 60 * 1000:
        return False

    for body in _webhook_body_candidates(raw_body):
        expected = _sign(secret, body, ts)
        if hmac.compare_digest(sig, expected.lower()):
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
    shop_id = _shop_id()
    secret = _secret_key()
    if not shop_id:
        return False, "PAYPLAT_SHOP_ID is empty"
    if not secret:
        return False, "PAYPLAT_SECRET_KEY is empty"
    base = _api_base()
    if not base:
        return False, "PAYPLAT_API_BASE is empty"

    payload = json_payload or {}
    body = ""
    if method.upper() != "GET" and payload:
        body = _canonical_body(payload)
    url = f"{base}/{path.lstrip('/')}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.PAYPLAT_OUT_REQUEST,
        body=payload if payload else {"_method": method, "_path": path},
        http_method=method,
        url=url,
        note="PayPlat API",
    )
    try:
        headers = _headers(body=body)
        if method.upper() == "GET" or not body:
            r = requests.request(method, url, headers=headers, timeout=timeout)
        else:
            r = requests.request(method, url, data=body.encode("utf-8"), headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("PayPlat %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.PAYPLAT_OUT_RESPONSE,
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
        direction=Direction.PAYPLAT_OUT_RESPONSE,
        body=resp_body,
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="PayPlat API",
    )
    if not isinstance(resp_body, dict):
        return False, {"error": str(resp_body)}
    if not r.ok:
        return False, resp_body
    return True, resp_body


def payplat_create_deal(
    *,
    amount: Decimal,
    shop_internal_id: str,
    requisite_type: str | None = None,
    id_contragent: str | None = None,
    bank: str | None = None,
    tariff: str | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    payload: dict[str, Any] = {
        "shop_internal_id": shop_internal_id,
        "shop_id": _shop_id(),
        "amount": _format_amount(amount),
    }
    req_type = (requisite_type or payplat_requisite_type_for(None)).strip().lower()
    if req_type:
        payload["requisite_type"] = req_type
    if id_contragent:
        payload["id_contragent"] = id_contragent
    elif req_type in _REQUISITE_TYPES_NEED_CONTRAGENT:
        payload["id_contragent"] = shop_internal_id
    if bank:
        payload["bank"] = bank
    tariff_val = (tariff or payplat_tariff()).strip().upper()
    if tariff_val:
        payload["tariff"] = tariff_val
    return _request("POST", "/deals", json_payload=payload, pay_in=pay_in)


def payplat_cancel_deal(*, shop_internal_id: str, pay_in=None) -> tuple[bool, dict[str, Any] | str]:
    sid = (shop_internal_id or "").strip()
    if not sid:
        return False, "shop_internal_id is empty"
    return _request("POST", f"/order/cancel/{sid}", json_payload={}, pay_in=pay_in)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def payplat_is_soft_rejection(body: dict) -> bool:
    if not isinstance(body, dict):
        return False
    return _norm_status(body.get("status")) == "amount_currently_unavailable"


def resolve_payplat_webhook_session(
    *,
    shop_internal_id: str | None,
    order_id: str | int | None = None,
) -> PayplatPayInSession | None:
    from payments.models import PayIn, PayplatPayInSession

    sid = (shop_internal_id or "").strip()
    oid = str(order_id).strip() if order_id not in (None, "") else ""

    if sid:
        session = (
            PayplatPayInSession.objects.filter(external_id=sid)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session is not None:
            return session

    if oid:
        session = (
            PayplatPayInSession.objects.filter(provider_order_id=oid)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session is not None:
            return session

    if not sid:
        return None

    pay_in = PayIn.objects.filter(pk=sid).select_related("order__payment_details__group__trader").first()
    if pay_in is None or pay_in.order is None or pay_in.order.payment_details is None:
        return None
    if not is_payplat_trader(pay_in.order.payment_details.group.trader):
        return None

    session, created = PayplatPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": str(pay_in.id), "create_response": {}, "last_webhook_payload": {}},
    )
    updates: list[str] = []
    if str(session.external_id) != str(pay_in.id):
        session.external_id = str(pay_in.id)
        updates.append("external_id")
    if oid and not session.provider_order_id:
        session.provider_order_id = oid
        updates.append("provider_order_id")
    if updates:
        updates.append("updated_at")
        session.save(update_fields=updates)
    if created:
        logger.info("PayPlat webhook: recovered session for PayIn=%s shop_internal_id=%s", pay_in.id, sid)
    return session


def payplat_webhook_outcome(body: dict) -> str | None:
    """success | fail | None (ignore intermediate)."""
    status = _norm_status(body.get("status"))
    if status == "success":
        return "success"
    if status in ("timeout", "expired", "failure", "cancelled", "error"):
        return "fail"
    dispute_status = _norm_status(body.get("dispute_status"))
    if dispute_status == "accepted" and status == "success":
        return "success"
    return None


def payplat_map_requisite(create_body: dict) -> dict:
    """Маппинг ответа POST /deals в payment_details для мерчанта (только H2H card/phone, не redirect)."""
    if not isinstance(create_body, dict):
        return {}

    requisite = create_body.get("requisite")
    if isinstance(requisite, dict):
        card = (requisite.get("card_number") or "").strip()
        phone = (requisite.get("phone_number") or "").strip()
        owner = requisite.get("holder_name") or ""
        bank = requisite.get("bank") or ""
        if card:
            digits = "".join(c for c in card if c.isdigit())
            return {"card_number": digits[:16] if len(digits) >= 16 else card, "owner": owner, "bank": bank}
        if phone:
            digits = "".join(c for c in phone if c.isdigit())
            return {
                "phone": phone if phone.startswith("+") else (f"+{digits}" if digits else phone),
                "owner": owner,
                "bank": bank,
            }

    top_phone = (create_body.get("phone_number") or "").strip()
    if top_phone:
        digits = "".join(c for c in top_phone if c.isdigit())
        return {
            "phone": top_phone if top_phone.startswith("+") else (f"+{digits}" if digits else top_phone),
            "owner": "",
            "bank": "",
        }

    invoice = create_body.get("invoice")
    if isinstance(invoice, dict):
        payment_data = invoice.get("payment_data")
        if isinstance(payment_data, dict):
            card = (payment_data.get("card_number") or "").strip()
            owner = payment_data.get("card_holder") or payment_data.get("holder_name") or ""
            bank = payment_data.get("bank") or ""
            if card:
                digits = "".join(c for c in card if c.isdigit())
                return {
                    "card_number": digits[:16] if len(digits) >= 16 else card,
                    "owner": owner,
                    "bank": bank,
                }
            phone = (payment_data.get("phone_number") or payment_data.get("phone") or "").strip()
            if phone:
                digits = "".join(c for c in phone if c.isdigit())
                return {
                    "phone": phone if phone.startswith("+") else (f"+{digits}" if digits else phone),
                    "owner": owner,
                    "bank": bank,
                }

    return {}


def payplat_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import PayplatPayInSession

    s = PayplatPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = payplat_map_requisite(s.create_response or {})
    from payments.psp_payin import requisite_payload_has_fields

    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = payplat_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def try_attach_payplat_session(pay_in: Any) -> bool | None:
    """PayPlat API для виртуальной группы payplat1."""
    from payments.models import PayplatPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_payplat_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    external_id = str(pay_in.id)
    ps_name = pay_in.payment_system.name if pay_in.payment_system else None
    requisite_type = payplat_requisite_type_for(ps_name)
    bank = payplat_bank_for(ps_name)

    session, _ = PayplatPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": external_id, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = external_id
    session.save(update_fields=["external_id", "updated_at"])

    id_contragent = external_id
    if pay_in.client_id and getattr(pay_in, "client", None):
        id_contragent = str(pay_in.client.client_id)

    ok, data = payplat_create_deal(
        amount=pay_in.amount,
        shop_internal_id=external_id,
        requisite_type=requisite_type,
        id_contragent=id_contragent,
        bank=bank,
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("PayPlat create deal failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    if payplat_is_soft_rejection(session.create_response):
        order_id = str((data or {}).get("order_id") or "")
        session.create_response = {
            "error": "amount_currently_unavailable",
            "upstream": session.create_response,
        }
        session.provider_order_id = order_id
        session.save(update_fields=["create_response", "provider_order_id", "updated_at"])
        if order_id:
            payplat_cancel_deal(shop_internal_id=external_id, pay_in=pay_in)
        logger.error("PayPlat: soft rejection PayIn=%s", pay_in.id)
        return False

    session.provider_order_id = str((session.create_response or {}).get("order_id") or "")
    session.save(update_fields=["create_response", "provider_order_id", "updated_at"])

    req = payplat_map_requisite(session.create_response)
    from payments.psp_payin import requisite_payload_has_fields

    if not requisite_payload_has_fields(req):
        upstream = session.create_response
        order_id = session.provider_order_id
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": upstream,
        }
        session.provider_order_id = ""
        session.save(update_fields=["create_response", "provider_order_id", "updated_at"])
        if order_id:
            payplat_cancel_deal(shop_internal_id=external_id, pay_in=pay_in)
        logger.error(
            "PayPlat: no requisite PayIn=%s status=%s",
            pay_in.id,
            _norm_status((upstream or {}).get("status")),
        )
        return False
    return True


def payplat_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import PayplatPayInSession

    try:
        s = PayplatPayInSession.objects.get(pay_in=pay_in)
    except PayplatPayInSession.DoesNotExist:
        return
    if not s.external_id:
        return
    ok, data = payplat_cancel_deal(shop_internal_id=s.external_id, pay_in=pay_in)
    if not ok:
        logger.warning("PayPlat cancel failed PayIn=%s: %s", pay_in.id, data)
