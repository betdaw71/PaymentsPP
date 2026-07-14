"""Поля платёжной страницы для obtain API."""
from __future__ import annotations

from payments.bank_deeplinks import build_bank_actions, build_transfer_clipboard
from payments.integrations.melbet.mapping import sender_bank_for_melbet_method
from payments.models import PayIn


def _sender_bank_for_payin(pay_in: PayIn) -> str | None:
    if not hasattr(pay_in, "melbet_session"):
        return None
    return sender_bank_for_melbet_method(pay_in.melbet_session.melbet_method)


def resolve_locale(pay_in: PayIn, lang_hint: str | None = None) -> str:
    hint = (lang_hint or "").strip().lower()
    if hint in ("kk", "ru", "kz"):
        return "kk" if hint in ("kk", "kz") else "ru"
    if pay_in.currency and (pay_in.currency.symbol or "").upper() == "KZT":
        return "kk"
    return "ru"


def enrich_for_payment_page(data: dict, pay_in: PayIn, *, locale: str | None = None) -> dict:
    locale = locale or resolve_locale(pay_in)
    currency = data.get("currency") or (pay_in.currency.symbol if pay_in.currency else "")
    pd = data.get("payment_details") or {}
    order_status = None
    if pay_in.order and pay_in.order.status:
        order_status = pay_in.order.status.name

    data["locale"] = locale
    data["order_status"] = order_status
    data["pending_verification"] = order_status in ("Money sent by user", "Arbitrage")

    if pd and data.get("status") not in ("Success", "Failed", "Declined"):
        data["bank_actions"] = build_bank_actions(
            amount=pay_in.amount,
            currency=currency,
            payment_details=pd,
            locale=locale,
            sender_bank=_sender_bank_for_payin(pay_in),
        )
        data["clipboard_text"] = build_transfer_clipboard(
            amount=pay_in.amount,
            currency=currency,
            payment_details=pd,
            locale=locale,
        )
    else:
        data.setdefault("bank_actions", [])
        data.setdefault("clipboard_text", "")

    return data
