"""HTTP client for PrismaPay (Spyder merchant API @ https://prismapay.software).

Local KGS Melbet mapping (Spyder paymentMethod):
  C2CKGS  → card
  PHONEKGS → phone
  QRKGS   → qr

Same protocol as Nexus/Spyder (POST /api/orders type=sell, HMAC callback INTELPAY_V1).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_SIG_RE = re.compile(r"^v1=[0-9a-fA-F]{64}$")
_TS_RE = re.compile(r"^[0-9]{1,12}$")


def prisma_trader_username() -> str:
    return getattr(settings, "PRISMA_TRADER_USERNAME", "prisma1")


def is_prisma_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    expected = prisma_trader_username()
    actual = (trader.user.username or "").strip()
    return actual.lower() == expected.lower()


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


def prisma_payment_method_for(payment_system_name: str | None) -> str:
    """Spyder paymentMethod for our PS names — local KGS: card / phone / qr."""
    ps = (payment_system_name or "").strip()
    mapped = _parse_json_map("PRISMA_PAYMENT_METHOD_MAP")
    if ps and ps in mapped and mapped[ps].strip():
        return mapped[ps].strip().lower()
    default = (getattr(settings, "PRISMA_PAYMENT_METHOD", None) or "").strip()
    if default:
        return default.lower()
    upper = ps.upper()
    if upper in ("PHONEKGS", "PHONEKZT"):
        return "phone"
    if upper in ("QRKGS", "QR"):
        return "qr"
    if upper in ("C2CKGS", "C2CKZT", "C2C", "C2CKZTTEST"):
        return "card"
    return "card"


def prisma_callback_url() -> str:
    explicit = (getattr(settings, "PRISMA_CALLBACK_URL", None) or "").strip().rstrip("/")
    if explicit:
        return f"{explicit}/"
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/prisma/"


def _api_token() -> str:
    return (getattr(settings, "PRISMA_API_TOKEN", None) or "").strip()


def _callback_secret() -> str:
    return (getattr(settings, "PRISMA_CALLBACK_SECRET", None) or "").strip()


def _api_base() -> str:
    return (getattr(settings, "PRISMA_API_BASE", "https://prismapay.software") or "").rstrip("/")


def _timeout_seconds() -> int:
    try:
        return int(getattr(settings, "PRISMA_TIMEOUT_SECONDS", 900) or 900)
    except (TypeError, ValueError):
        return 900


def _amount_number(amount: Decimal):
    d = Decimal(str(amount))
    if d == d.to_integral_value():
        return int(d)
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def verify_prisma_callback(*, raw_body: bytes, headers, secret: str | None = None) -> bool:
    """Spyder INTELPAY_V1: HMAC-SHA256(callback_id.timestamp. + raw_body)."""
    if getattr(settings, "PRISMA_WEBHOOK_SKIP_VERIFY", False):
        logger.warning("Prisma webhook: PRISMA_WEBHOOK_SKIP_VERIFY is enabled")
        return True
    secret = (secret if secret is not None else _callback_secret()).strip()
    if not secret:
        logger.warning("Prisma webhook: PRISMA_CALLBACK_SECRET empty — accepting unsigned callback")
        return True

    def _h(name: str) -> str:
        if hasattr(headers, "get"):
            return str(headers.get(name) or headers.get(name.lower()) or "").strip()
        return ""

    callback_id = _h("X-Callback-Id") or _h("x-callback-id")
    timestamp = _h("X-Callback-Timestamp") or _h("x-callback-timestamp")
    signature = _h("X-Callback-Signature") or _h("x-callback-signature")
    if not callback_id or len(callback_id) > 200:
        return False
    if not _TS_RE.fullmatch(timestamp) or not _SIG_RE.fullmatch(signature):
        return False
    now = int(time.time())
    sent_at = int(timestamp)
    if sent_at < now - 300 or sent_at > now + 60:
        return False
    prefix = f"{callback_id}.{timestamp}.".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), prefix + (raw_body or b""), hashlib.sha256).hexdigest()
    actual = signature[3:]
    return hmac.compare_digest(expected.lower(), actual.lower())


def _request(
    method: str,
    path: str,
    *,
    json_payload: dict | None = None,
    timeout: int = 60,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    token = _api_token()
    if not token:
        return False, "PRISMA_API_TOKEN is empty"
    base = _api_base()
    if not base:
        return False, "PRISMA_API_BASE is empty"

    payload = json_payload or {}
    url = f"{base}/{path.lstrip('/')}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.PRISMA_OUT_REQUEST,
        body=payload if payload else {"_method": method, "_path": path},
        http_method=method,
        url=url,
        note="Prisma/Spyder API",
    )
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        if method.upper() == "GET" or not payload:
            r = requests.request(method, url, headers=headers, timeout=timeout)
        else:
            headers["Content-Type"] = "application/json"
            r = requests.request(
                method,
                url,
                headers=headers,
                data=json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
                timeout=timeout,
            )
    except requests.RequestException as exc:
        logger.exception("Prisma %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.PRISMA_OUT_RESPONSE,
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
        direction=Direction.PRISMA_OUT_RESPONSE,
        body=resp_body,
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="Prisma/Spyder API",
    )
    if not r.ok:
        return False, resp_body if isinstance(resp_body, dict) else {"error": str(resp_body)}
    if not isinstance(resp_body, dict):
        return False, {"error": "unexpected_response_shape", "upstream": resp_body}
    data = resp_body.get("data") if isinstance(resp_body.get("data"), dict) else resp_body
    return True, data if isinstance(data, dict) else resp_body


def prisma_create_sell(
    *,
    amount: Decimal,
    order_id: str,
    currency: str,
    payment_method: str,
    payment_bank: str | None = None,
    payment_client: str | None = None,
    timeout_seconds: int | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    payload: dict[str, Any] = {
        "type": "sell",
        "amountIn": _amount_number(amount),
        "baseCurrency": (currency or "KGS").strip().upper() or "KGS",
        "quoteCurrency": "USDT",
        "paymentMethod": (payment_method or "card").strip().lower() or "card",
        "orderId": order_id,
        "timeoutSeconds": int(timeout_seconds if timeout_seconds is not None else _timeout_seconds()),
    }
    bank = (payment_bank or getattr(settings, "PRISMA_PAYMENT_BANK", None) or "").strip()
    if bank:
        payload["paymentBank"] = bank
    client = (payment_client or getattr(settings, "PRISMA_PAYMENT_CLIENT", None) or "").strip()
    if client:
        payload["paymentClient"] = client[:255]
    return _request("POST", "/api/orders", json_payload=payload, pay_in=pay_in)


def prisma_cancel_order(*, provider_id: str, pay_in=None) -> tuple[bool, dict[str, Any] | str]:
    provider_id = (provider_id or "").strip()
    if not provider_id:
        return False, "provider_id is empty"
    return _request("POST", f"/api/orders/{provider_id}/cancel", json_payload=None, pay_in=pay_in)


def _norm_status(raw: str | None) -> str:
    if not isinstance(raw, str):
        return ""
    return raw.strip().upper().replace("-", "_")


def resolve_prisma_webhook_session(*, order_id: str | None, provider_id: str | None):
    from payments.models import PayIn, PrismaPayInSession

    oid = (order_id or "").strip()
    pid = (provider_id or "").strip()
    if oid:
        session = (
            PrismaPayInSession.objects.filter(external_id=oid)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
        if session is not None:
            return session
        pay_in = PayIn.objects.filter(pk=oid).select_related("order__payment_details__group__trader").first()
        if pay_in is not None and pay_in.order and pay_in.order.payment_details:
            if is_prisma_trader(pay_in.order.payment_details.group.trader):
                session, _ = PrismaPayInSession.objects.get_or_create(
                    pay_in=pay_in,
                    defaults={
                        "external_id": str(pay_in.id),
                        "create_response": {},
                        "last_webhook_payload": {},
                    },
                )
                return session
    if pid:
        return (
            PrismaPayInSession.objects.filter(provider_order_id=pid)
            .select_related("pay_in", "pay_in__order")
            .first()
        )
    return None


def prisma_webhook_outcome(body: dict) -> str | None:
    status = _norm_status(body.get("status"))
    if status in ("SUCCESS", "UPDATED"):
        return "success"
    if status in ("CANCELLED", "CANCELED", "EXPIRED", "NO_REQUISITES"):
        return "fail"
    return None


def prisma_is_webhook_body(body: dict | None) -> bool:
    if not isinstance(body, dict):
        return False
    if str(body.get("type") or "").strip().lower() == "sell" and (body.get("id") or body.get("orderId")):
        return True
    return bool(body.get("orderId") and body.get("status") and body.get("amountIn") is not None)


def prisma_webhook_paid_amount(body: dict | None) -> Decimal | None:
    if not prisma_is_webhook_body(body):
        return None
    assert isinstance(body, dict)
    for key in ("amountIn", "amount_in", "amount"):
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


def prisma_success_webhook_allows_completed_recalc(body: dict | None) -> bool:
    if not isinstance(body, dict):
        return False
    return prisma_is_webhook_body(body) and prisma_webhook_outcome(body) == "success"


def prisma_map_requisite(create_body: dict) -> dict:
    body = create_body if isinstance(create_body, dict) else {}
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    details = str(data.get("paymentDetails") or "").strip()
    owner = str(data.get("paymentFullName") or data.get("paymentClient") or "").strip()
    bank = str(data.get("paymentBank") or "").strip()
    method = str(data.get("paymentMethod") or "").strip().lower()
    link = str(data.get("paymentLink") or "").strip()
    qr_image = str(data.get("qrImageUrl") or data.get("qr_image_url") or "").strip()
    qr_link = str(data.get("qrPaymentLink") or data.get("qr_payment_link") or "").strip()
    raw_qr = str(data.get("raw") or "").strip()
    digits = "".join(c for c in details if c.isdigit())

    if method == "qr":
        out: dict[str, str] = {"bank": bank, "owner": owner}
        payload = raw_qr or details
        if payload:
            out["qr_payload"] = payload
        if qr_image:
            out["qr_image_url"] = qr_image
        elif qr_link:
            out["qr_image_url"] = qr_link
            out["payment_form_url"] = qr_link
        elif link:
            out["payment_form_url"] = link
        return out

    if method == "phone" or (details.startswith("+") and len(digits) >= 10):
        formatted = details if details.startswith("+") else (f"+{digits}" if digits else details)
        out = {"phone": formatted, "owner": owner, "bank": bank}
        if link:
            out["payment_form_url"] = link
        return out

    if len(digits) >= 13:
        out = {"card_number": digits[:19], "owner": owner, "bank": bank}
        if link:
            out["payment_form_url"] = link
        return out
    if details:
        out = {"card_number": details, "owner": owner, "bank": bank}
        if link:
            out["payment_form_url"] = link
        return out
    return {}


def prisma_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import PrismaPayInSession
    from payments.psp_payin import requisite_payload_has_fields

    s = PrismaPayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = prisma_map_requisite(s.create_response or {})
    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = prisma_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def try_attach_prisma_session(pay_in: Any) -> bool | None:
    from payments.models import PrismaPayInSession
    from payments.psp_payin import payin_routed_group_matches_ps, requisite_payload_has_fields

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_prisma_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    external_id = str(pay_in.id)
    ps_name = pay_in.payment_system.name if pay_in.payment_system else None
    currency = ""
    if pay_in.currency:
        currency = (pay_in.currency.symbol or "").strip().upper()
    session, _ = PrismaPayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={
            "external_id": external_id,
            "create_response": {},
            "last_webhook_payload": {},
        },
    )
    session.external_id = external_id
    session.save(update_fields=["external_id", "updated_at"])

    ok, data = prisma_create_sell(
        amount=pay_in.amount,
        order_id=external_id,
        currency=currency or "KGS",
        payment_method=prisma_payment_method_for(ps_name),
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Prisma create sell failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    session.provider_order_id = str((session.create_response or {}).get("id") or "")
    session.save(update_fields=["create_response", "provider_order_id", "updated_at"])

    st = _norm_status((session.create_response or {}).get("status"))
    if st in ("NO_REQUISITES", "CANCELLED", "CANCELED", "EXPIRED"):
        logger.error("Prisma create sell status=%s PayIn=%s", st, pay_in.id)
        return False
    req = prisma_map_requisite(session.create_response)
    if not requisite_payload_has_fields(req):
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Prisma: no requisite PayIn=%s", pay_in.id)
        return False
    return True


def prisma_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import PrismaPayInSession

    try:
        s = PrismaPayInSession.objects.get(pay_in=pay_in)
    except PrismaPayInSession.DoesNotExist:
        return
    if not s.provider_order_id:
        return
    ok, data = prisma_cancel_order(provider_id=s.provider_order_id, pay_in=pay_in)
    if not ok:
        logger.warning("Prisma cancel failed PayIn=%s: %s", pay_in.id, data)
