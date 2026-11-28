"""Поля платёжной страницы для obtain API."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from merchant.kzt_settlement import is_melbet_merchant, melbet_kgs_ps_names
from payments.bank_deeplinks import build_bank_actions, build_transfer_clipboard
from payments.bank_guides import build_bank_guides
from payments.integrations.melbet.mapping import sender_bank_for_melbet_method
from payments.models import PayIn
from payments.receipt_policy import has_receipt_for_payin, receipt_required_for_payin


def _melbet_method(pay_in: PayIn) -> str:
    from django.core.exceptions import ObjectDoesNotExist

    try:
        session = pay_in.melbet_session
    except ObjectDoesNotExist:
        return ""
    if session is None:
        return ""
    return (session.melbet_method or "").strip().lower()


def _sender_bank_for_payin(pay_in: PayIn) -> str | None:
    return sender_bank_for_melbet_method(_melbet_method(pay_in) or None)


def _ps_name(pay_in: PayIn) -> str:
    ps = getattr(pay_in, "payment_system", None)
    return (getattr(ps, "name", None) or "").strip().upper()


def _is_kgs_payment(pay_in: PayIn, currency: str) -> bool:
    if (currency or "").upper() in {"KGS", "KGZ"}:
        return True
    return _ps_name(pay_in) in melbet_kgs_ps_names()


def resolve_locale(pay_in: PayIn, lang_hint: str | None = None) -> str:
    hint = (lang_hint or "").strip().lower()
    if hint in ("kk", "ru", "kz"):
        return "kk" if hint in ("kk", "kz") else "ru"
    # Локальный KGS (QR/card/phone) — русский, не казахский (Kaspi-трансгран).
    cur = ""
    if getattr(pay_in, "currency", None):
        cur = (pay_in.currency.symbol or "").upper()
    if _is_kgs_payment(pay_in, cur):
        return "ru"
    if is_melbet_merchant(getattr(pay_in, "merchant", None)):
        return "kk"
    if cur == "KZT":
        return "kk"
    return "ru"


def _requisites_available(data: dict, pay_in: PayIn) -> bool:
    status_name = pay_in.status.name if pay_in.status else ""
    if status_name in ("Declined", "Failed"):
        return False
    order_status = pay_in.order.status.name if pay_in.order and pay_in.order.status else ""
    if order_status == "Cannot process":
        return False
    pd = data.get("payment_details") or {}
    return bool(
        pd.get("card_number")
        or pd.get("phone")
        or pd.get("deposit_number")
        or pd.get("payment_form_url")
        or pd.get("deeplink")
        or pd.get("qr_image_url")
    )


def transfer_quote_for_page(pay_in: PayIn, currency: str) -> tuple[Decimal, str]:
    """Сумма на платёжной странице и в deeplink — валюта заявки."""
    fiat = pay_in.amount if pay_in.amount is not None else Decimal("0")
    cur = (currency or "").upper()
    return fiat, cur or (currency or "")


def _format_transfer_amount(amount: Decimal, currency: str) -> str:
    if (currency or "").upper() == "USD":
        return f"{amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
    text = format(amount, "f") if isinstance(amount, Decimal) else str(amount)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _is_qr_or_widget_only(pd: dict) -> bool:
    if not isinstance(pd, dict):
        return False
    has_h2h = bool(pd.get("card_number") or pd.get("phone") or pd.get("deposit_number"))
    if has_h2h:
        return False
    return bool(pd.get("qr_image_url") or pd.get("payment_form_url") or pd.get("deeplink"))


def page_mode_for_payin(pay_in: PayIn, pd: dict | None = None) -> str:
    """Режим UI: qr | phone | card_kgs | h2h (Kaspi/Halyk KZT)."""
    pd = pd if isinstance(pd, dict) else {}
    ps = _ps_name(pay_in)
    method = _melbet_method(pay_in)
    if ps == "QRKGS" or method in {"qr_kgs", "lkq", "elqr", "qr"} or method.endswith("_qr"):
        return "qr"
    if ps == "PHONEKGS" or "phone_kgs" in method or "mobile_kgs" in method:
        return "phone"
    if ps == "C2CKGS" or "card2card_kgs" in method or method in {"card_kgs", "c2ckgs"}:
        return "card_kgs"
    if _is_qr_or_widget_only(pd):
        return "qr"
    if pd.get("phone") and not pd.get("card_number"):
        return "phone"
    return "h2h"


def enrich_for_payment_page(data: dict, pay_in: PayIn, *, locale: str | None = None) -> dict:
    locale = locale or resolve_locale(pay_in)
    currency = data.get("currency") or (pay_in.currency.symbol if pay_in.currency else "")
    pd = data.get("payment_details") or {}
    order_status = None
    if pay_in.order and pay_in.order.status:
        order_status = pay_in.order.status.name

    xfer_amt, xfer_cur = transfer_quote_for_page(pay_in, currency)
    xfer_amt_text = _format_transfer_amount(xfer_amt, xfer_cur)
    mode = page_mode_for_payin(pay_in, pd)

    data["locale"] = locale
    data["order_status"] = order_status
    data["pending_verification"] = order_status in ("Money sent by user", "Arbitrage")
    data["receipt_required"] = receipt_required_for_payin(pay_in)
    data["receipt_uploaded"] = has_receipt_for_payin(pay_in)
    data["requisites_available"] = _requisites_available(data, pay_in)
    data["transfer_amount"] = xfer_amt_text
    data["transfer_currency"] = xfer_cur
    data["page_mode"] = mode
    data["melbet_method"] = _melbet_method(pay_in)
    data["show_fx_note"] = mode == "h2h"
    data["show_lang_kk"] = mode == "h2h"
    if not data.get("expires_at") and pay_in.created_at and getattr(pay_in, "payment_system", None):
        ttl = getattr(pay_in.payment_system, "expired_time_in", None)
        if ttl is not None:
            data["expires_at"] = int((pay_in.created_at + ttl).timestamp())

    # Kaspi/Halyk только для KZT-трансгран (h2h).
    if pd and data.get("status") not in ("Success", "Failed", "Declined") and mode == "h2h":
        data["bank_actions"] = build_bank_actions(
            amount=xfer_amt_text,
            currency=xfer_cur,
            payment_details=pd,
            locale=locale,
            sender_bank=_sender_bank_for_payin(pay_in),
        )
        data["clipboard_text"] = build_transfer_clipboard(
            amount=xfer_amt_text,
            currency=xfer_cur,
            payment_details=pd,
            locale=locale,
        )
        data["bank_guides"] = build_bank_guides(
            currency=currency,
            locale=locale,
            bank_actions=data.get("bank_actions"),
        )
    else:
        data["bank_actions"] = []
        data["clipboard_text"] = ""
        data["bank_guides"] = []

    return data
