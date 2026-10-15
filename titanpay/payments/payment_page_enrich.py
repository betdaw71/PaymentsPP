"""Поля платёжной страницы для obtain API."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from merchant.kzt_settlement import is_melbet_merchant
from payments.bank_deeplinks import build_bank_actions, build_transfer_clipboard
from payments.bank_guides import build_bank_guides
from payments.integrations.melbet.mapping import sender_bank_for_melbet_method
from payments.models import PayIn
from payments.receipt_policy import has_receipt_for_payin, receipt_required_for_payin


def _sender_bank_for_payin(pay_in: PayIn) -> str | None:
    from django.core.exceptions import ObjectDoesNotExist

    try:
        session = pay_in.melbet_session
    except ObjectDoesNotExist:
        return None
    if session is None:
        return None
    return sender_bank_for_melbet_method(session.melbet_method)


def resolve_locale(pay_in: PayIn, lang_hint: str | None = None) -> str:
    hint = (lang_hint or "").strip().lower()
    if hint in ("kk", "ru", "kz"):
        return "kk" if hint in ("kk", "kz") else "ru"
    if pay_in.currency and (pay_in.currency.symbol or "").upper() == "KZT":
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
    """Сумма, которую плательщик вводит в банке.

    Melbet C2CKZT — международный перевод в USD (order.usd_amount).
    Заявка мерчанта и сверка остаются в KZT (pay_in.amount).
    """
    fiat = pay_in.amount if pay_in.amount is not None else Decimal("0")
    cur = (currency or "").upper()
    if is_melbet_merchant(getattr(pay_in, "merchant", None)) and cur == "KZT":
        order = getattr(pay_in, "order", None)
        raw = getattr(order, "usd_amount", None) if order is not None else None
        try:
            usd = Decimal(str(raw)) if raw is not None else Decimal("0")
        except (InvalidOperation, ValueError, TypeError):
            usd = Decimal("0")
        if usd > 0:
            return usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "USD"
    return fiat, cur or (currency or "")


def _format_transfer_amount(amount: Decimal, currency: str) -> str:
    if (currency or "").upper() == "USD":
        return f"{amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
    text = format(amount, "f") if isinstance(amount, Decimal) else str(amount)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def enrich_for_payment_page(data: dict, pay_in: PayIn, *, locale: str | None = None) -> dict:
    locale = locale or resolve_locale(pay_in)
    currency = data.get("currency") or (pay_in.currency.symbol if pay_in.currency else "")
    pd = data.get("payment_details") or {}
    order_status = None
    if pay_in.order and pay_in.order.status:
        order_status = pay_in.order.status.name

    xfer_amt, xfer_cur = transfer_quote_for_page(pay_in, currency)
    xfer_amt_text = _format_transfer_amount(xfer_amt, xfer_cur)

    data["locale"] = locale
    data["order_status"] = order_status
    data["pending_verification"] = order_status in ("Money sent by user", "Arbitrage")
    data["receipt_required"] = receipt_required_for_payin(pay_in)
    data["receipt_uploaded"] = has_receipt_for_payin(pay_in)
    data["requisites_available"] = _requisites_available(data, pay_in)
    data["transfer_amount"] = xfer_amt_text
    data["transfer_currency"] = xfer_cur

    if pd and data.get("status") not in ("Success", "Failed", "Declined"):
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
        data.setdefault("bank_actions", [])
        data.setdefault("clipboard_text", "")
        data.setdefault("bank_guides", [])

    return data
