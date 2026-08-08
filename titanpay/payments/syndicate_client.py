"""HTTP client for Syndicate Pay PSP (https://api.syndicate-pay.com, H2H)."""
from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

OPERATION_DEPOSIT = "Пополнение"


def syndicate_trader_username() -> str:
    return getattr(settings, "SYNDICATE_TRADER_USERNAME", "syndicate1")


def is_syndicate_trader(trader) -> bool:
    if trader is None or not getattr(trader, "user", None):
        return False
    return trader.user.username == syndicate_trader_username()


def syndicate_callback_url() -> str:
    base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
    return f"{base}/api/v1/webhooks/psp/syndicate/"


def _api_base() -> str:
    return (getattr(settings, "SYNDICATE_API_BASE", "https://api.syndicate-pay.com") or "").rstrip("/")


def _api_key() -> str:
    return (getattr(settings, "SYNDICATE_API_KEY", None) or "").strip()


def _merchant_login() -> str:
    return (getattr(settings, "SYNDICATE_MERCHANT_LOGIN", None) or "").strip()


def _merchant_id() -> int | None:
    raw = (getattr(settings, "SYNDICATE_MERCHANT_ID", None) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def format_sum_for_signature(amount: Decimal) -> str:
    """Как в доке Syndicate: целые без .00, иначе 2 знака."""
    d = Decimal(str(amount)).quantize(Decimal("0.01"))
    if d == d.to_integral_value():
        return str(int(d))
    return f"{d:.2f}"


def sign_create_order(*, login: str, amount: Decimal, invid: str, api_key: str) -> str:
    sum_str = format_sum_for_signature(amount)
    payload = f"{login}:{sum_str}:{invid}:{api_key}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sign_callback(*, sum_str: str, invid: str, api_key: str) -> str:
    return hashlib.sha256(f"{sum_str}:{invid}:{api_key}".encode("utf-8")).hexdigest()


def sign_unclaimed(*, login: str, order_ref: str, api_key: str) -> str:
    return hashlib.sha256(f"{login}:{order_ref}:{api_key}".encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _banks_catalog() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "data" / "syndicate_banks.json"
    if not path.is_file():
        return {"banks": [], "payment_system_to_bank_code": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Syndicate banks catalog unreadable: %s", exc)
        return {"banks": [], "payment_system_to_bank_code": {}}
    if not isinstance(data, dict):
        return {"banks": [], "payment_system_to_bank_code": {}}
    return data


def syndicate_banks_list() -> list[dict[str, Any]]:
    """Справочник из banks-*.xlsx (259 записей) — code, name, nspk_code, …"""
    banks = _banks_catalog().get("banks")
    return banks if isinstance(banks, list) else []


def _env_bank_map() -> dict[str, str]:
    raw = getattr(settings, "SYNDICATE_BANK_MAP", None)
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            logger.warning("SYNDICATE_BANK_MAP is not valid JSON")
    return {}


def _bundled_ps_bank_map() -> dict[str, str]:
    raw = _banks_catalog().get("payment_system_to_bank_code")
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    from titanpay.settings import C2C_NAME, SBP_NAME

    return {C2C_NAME: "any-bank", SBP_NAME: "sbp"}


def _bank_map() -> dict[str, str]:
    """Bundled xlsx map + переопределения из SYNDICATE_BANK_MAP (.env)."""
    merged = dict(_bundled_ps_bank_map())
    merged.update(_env_bank_map())
    return merged


def _lookup_bank_code_in_catalog(payment_system_name: str) -> str | None:
    ps = (payment_system_name or "").strip()
    if not ps:
        return None
    pl = ps.lower()
    codes: dict[str, str] = {}
    names: list[tuple[str, str]] = []
    for bank in syndicate_banks_list():
        if not isinstance(bank, dict):
            continue
        code = (bank.get("code") or "").strip()
        name = (bank.get("name") or "").strip()
        if code:
            codes[code.lower()] = code
        if name:
            names.append((name.lower(), code))

    if pl in codes:
        return codes[pl]
    if pl.isdigit() and len(pl) >= 10:
        for bank in syndicate_banks_list():
            if isinstance(bank, dict) and str(bank.get("nspk_code") or "") == ps:
                return (bank.get("code") or "").strip() or None
    for nl, code in names:
        if nl == pl or pl in nl or nl in pl:
            return code or None
    return None


def syndicate_bank_for(payment_system_name: str) -> str | None:
    ps = (payment_system_name or "").strip()
    if not ps:
        return None
    mapped = _bank_map().get(ps)
    if not mapped:
        for key, val in _bank_map().items():
            if key.lower() == ps.lower():
                mapped = val
                break
    if mapped:
        return mapped.strip() or None
    from_catalog = _lookup_bank_code_in_catalog(ps)
    if from_catalog:
        return from_catalog
    default = (getattr(settings, "SYNDICATE_DEFAULT_BANK", None) or "any-bank").strip()
    return default or None


def _headers() -> dict[str, str]:
    return {"Accept": "application/json", "Content-Type": "application/json"}


def _parse_response(r: requests.Response) -> tuple[bool, dict[str, Any] | str]:
    try:
        body = r.json() if r.content else {}
    except ValueError:
        body = {"raw": r.text[:2000]}
    if not isinstance(body, dict):
        return False, {"error": str(body)}
    if not r.ok:
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
    base = _api_base()
    if not base:
        return False, "SYNDICATE_API_BASE is empty"

    url = f"{base}/{path.lstrip('/')}"
    from payments.payin_trace import Direction, trace_log

    trace_log(
        pay_in=pay_in,
        direction=Direction.SYNDICATE_OUT_REQUEST,
        body=json_payload or {},
        http_method=method,
        url=url,
        note="Syndicate API",
    )
    try:
        r = requests.request(method, url, json=json_payload, headers=_headers(), timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("Syndicate %s %s failed: %s", method, path, exc)
        trace_log(
            pay_in=pay_in,
            direction=Direction.SYNDICATE_OUT_RESPONSE,
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
        direction=Direction.SYNDICATE_OUT_RESPONSE,
        body=body if isinstance(body, dict) else {"payload": body},
        http_method=method,
        url=url,
        status_code=r.status_code,
        note="Syndicate API",
    )
    return ok, body


def syndicate_create_pay_in(
    *,
    amount: Decimal,
    invid: str,
    currency: str = "RUB",
    bank: str | None = None,
    client_id: str | None = None,
    client_ip: str | None = None,
    pay_in=None,
) -> tuple[bool, dict[str, Any] | str]:
    """POST /api/orders/create"""
    login = _merchant_login()
    api_key = _api_key()
    merchant_id = _merchant_id()
    if not login or not api_key or merchant_id is None:
        return False, "SYNDICATE_MERCHANT_LOGIN, SYNDICATE_API_KEY or SYNDICATE_MERCHANT_ID missing"

    signature = sign_create_order(login=login, amount=amount, invid=invid, api_key=api_key)
    sum_str = format_sum_for_signature(amount)
    payload: dict[str, Any] = {
        "currency": (currency or "RUB").upper(),
        "merchant": merchant_id,
        "invid": invid,
        "sum": sum_str,
        "signature": signature,
        "operation": OPERATION_DEPOSIT,
    }
    if bank:
        payload["bank"] = bank

    client_block: dict[str, Any] = {}
    if client_id:
        client_block["id"] = str(client_id)[:64]
    if client_ip:
        client_block["ip_address"] = client_ip
    if client_block:
        payload["client"] = client_block

    return _request("POST", "/api/orders/create", json_payload=payload, pay_in=pay_in)


def syndicate_unclaimed(*, invid: str, provider_order_id: int | None = None, pay_in=None) -> tuple[bool, dict[str, Any] | str]:
    """PUT /api/orders/unclaimed"""
    login = _merchant_login()
    api_key = _api_key()
    if not login or not api_key:
        return False, "SYNDICATE credentials missing"

    if provider_order_id is not None:
        ref = str(provider_order_id)
        payload = {"id": provider_order_id, "signature": sign_unclaimed(login=login, order_ref=ref, api_key=api_key)}
    else:
        ref = invid
        payload = {"invid": invid, "signature": sign_unclaimed(login=login, order_ref=ref, api_key=api_key)}

    return _request("PUT", "/api/orders/unclaimed", json_payload=payload, pay_in=pay_in)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def syndicate_webhook_outcome(body: dict) -> str | None:
    status = _norm_status(body.get("Status") or body.get("status"))
    if status == "completed":
        return "success"
    if status in ("cancelled", "unclaimed"):
        return "fail"
    return None


def _callback_sum_candidates(body: dict) -> list[str]:
    out: list[str] = []
    for key in ("OutSum", "outSum", "FactSum", "fact_sum", "sum"):
        val = body.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if not s:
            continue
        out.append(s)
        try:
            d = Decimal(s.replace(",", "."))
            out.append(format_sum_for_signature(d))
            if d == d.to_integral_value():
                out.append(str(int(d)))
        except (InvalidOperation, ValueError):
            pass
    return out


def verify_syndicate_callback_signature(body: dict) -> bool:
    if getattr(settings, "SYNDICATE_WEBHOOK_SKIP_VERIFY", False):
        logger.warning("Syndicate webhook: SYNDICATE_WEBHOOK_SKIP_VERIFY is enabled")
        return True

    api_key = _api_key()
    invid = str(body.get("InvId") or body.get("invid") or "").strip()
    sig = str(body.get("SignatureValue") or body.get("signature") or "").strip().lower()
    if not api_key or not invid or not sig:
        return False

    for sum_str in _callback_sum_candidates(body):
        expected = sign_callback(sum_str=sum_str, invid=invid, api_key=api_key)
        if expected.lower() == sig:
            return True
    return False


def syndicate_map_requisite(create_body: dict) -> dict:
    if not isinstance(create_body, dict):
        return {}

    widget_url = (create_body.get("widget_url") or "").strip()
    bank_name = (create_body.get("bank_ru_name") or create_body.get("bank") or "").strip()
    owner = (create_body.get("fio") or "").strip()
    is_sbp = bool(create_body.get("sbp"))
    is_account = bool(create_body.get("account_transfer"))

    card = create_body.get("card")
    if isinstance(card, dict):
        owner = owner or (card.get("fio") or "").strip()
        number = (card.get("number") or card.get("phone_number") or "").strip()
        telefon = (card.get("telefon") or "").strip()
        digits = "".join(c for c in number if c.isdigit())
        if is_sbp or create_body.get("bank") == "sbp":
            phone = telefon or number
            if phone and not phone.startswith("+"):
                phone = f"+{''.join(c for c in phone if c.isdigit())}"
            if phone:
                return {"phone": phone, "owner": owner, "bank": bank_name or "СБП"}
        if digits and len(digits) >= 13:
            return {"card_number": digits[:19], "owner": owner, "bank": bank_name}
        if number:
            return {"card_number": number.replace(" ", ""), "owner": owner, "bank": bank_name}

    company = create_body.get("company")
    if is_account and isinstance(company, dict):
        acct = (company.get("account_number") or "").replace(" ", "")
        if acct:
            return {
                "card_number": acct,
                "owner": (company.get("recipient_name") or owner or company.get("organization_name") or "").strip(),
                "bank": bank_name,
            }
        nspk = (company.get("nspk_link") or "").strip()
        if nspk:
            return {"payment_form_url": nspk, "owner": owner, "bank": bank_name}

    if widget_url:
        return {"payment_form_url": widget_url, "owner": owner, "bank": bank_name}

    return {}


def syndicate_requisite_for_payin(pay_in: Any) -> dict | None:
    from payments.models import SyndicatePayInSession
    from payments.psp_payin import requisite_payload_has_fields

    s = SyndicatePayInSession.objects.filter(pay_in_id=pay_in.pk).first()
    if s is None:
        return None
    req = syndicate_map_requisite(s.create_response or {})
    return req if requisite_payload_has_fields(req) else None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    req = syndicate_requisite_for_payin(pay_in)
    if req:
        representation["payment_details"] = req
    return representation


def syndicate_cancel_if_linked(pay_in: Any) -> None:
    from payments.models import SyndicatePayInSession

    try:
        s = SyndicatePayInSession.objects.get(pay_in=pay_in)
    except SyndicatePayInSession.DoesNotExist:
        return
    invid = s.external_id or str(pay_in.id)
    provider_id = None
    if s.provider_order_id:
        try:
            provider_id = int(s.provider_order_id)
        except ValueError:
            provider_id = None
    ok, data = syndicate_unclaimed(invid=invid, provider_order_id=provider_id, pay_in=pay_in)
    if not ok:
        logger.warning("Syndicate unclaimed failed PayIn=%s detail=%s", pay_in.id, data)


def try_attach_syndicate_session(pay_in: Any) -> bool | None:
    from payments.models import SyndicatePayInSession
    from payments.psp_payin import payin_routed_group_matches_ps

    if pay_in.order is None or pay_in.order.payment_details is None:
        return None
    trader = pay_in.order.payment_details.group.trader
    if not is_syndicate_trader(trader):
        return None
    if not payin_routed_group_matches_ps(pay_in):
        return False

    ps_name = pay_in.payment_system.name if pay_in.payment_system else ""
    currency = pay_in.currency.symbol if pay_in.currency else "RUB"
    invid = str(pay_in.id)
    bank = syndicate_bank_for(ps_name)

    session, _ = SyndicatePayInSession.objects.get_or_create(
        pay_in=pay_in,
        defaults={"external_id": invid, "create_response": {}, "last_webhook_payload": {}},
    )
    session.external_id = invid
    session.payment_system_name = ps_name
    session.save(update_fields=["external_id", "payment_system_name", "updated_at"])

    client_id = None
    if getattr(pay_in, "client_id", None) and getattr(pay_in, "client", None):
        client_id = str(pay_in.client.client_id)

    ok, data = syndicate_create_pay_in(
        amount=pay_in.amount,
        invid=invid,
        currency=currency,
        bank=bank,
        client_id=client_id,
        pay_in=pay_in,
    )
    if not ok:
        session.create_response = data if isinstance(data, dict) else {"error": str(data)}
        session.save(update_fields=["create_response", "updated_at"])
        logger.error("Syndicate create pay-in failed PayIn=%s: %s", pay_in.id, data)
        return False

    session.create_response = data if isinstance(data, dict) else {"payload": data}
    if isinstance(data, dict) and data.get("id") is not None:
        session.provider_order_id = str(data.get("id"))
    session.save(update_fields=["create_response", "provider_order_id", "updated_at"])

    req = syndicate_map_requisite(session.create_response)
    if not req:
        session.create_response = {
            "error": "no_payment_detail_in_response",
            "upstream": session.create_response,
        }
        session.provider_order_id = ""
        session.save(update_fields=["create_response", "provider_order_id", "updated_at"])
        syndicate_unclaimed(invid=invid, pay_in=pay_in)
        logger.error("Syndicate: no requisite PayIn=%s ps=%s", pay_in.id, ps_name)
        return False
    return True
