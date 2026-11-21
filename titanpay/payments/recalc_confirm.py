"""Admin-bot confirmation for a trader recalculation proposal."""
from __future__ import annotations

import logging
import re
from decimal import Decimal

import requests
from django.db import transaction
from rest_framework.exceptions import ValidationError

from payments.admin_alerts import _bot_token, _chat_id

logger = logging.getLogger(__name__)

_CALLBACK_RE = re.compile(r"^(rin|rout):(y|n):([0-9a-fA-F-]{36})$")


def parse_recalc_callback(data: str) -> tuple[str, str, bool] | None:
    match = _CALLBACK_RE.fullmatch((data or "").strip())
    if match is None:
        return None
    side, flag, order_id = match.groups()
    return side, order_id, flag == "y"


def format_recalc_prompt(
    *,
    side: str,
    order_id: str,
    merchant: str,
    trader: str,
    currency: str,
    amount,
    new_amount,
    merchant_order_id: str = "",
    pay_id: str = "",
    receipt: str = "",
) -> str:
    title = "Перерасчёт входящей заявки" if side == "rin" else "Перерасчёт выплаты"
    pay_label = "PayIn" if side == "rin" else "PayOut"
    lines = [
        title,
        "Нужно подтверждение.",
        "",
        f"Заявка: {order_id}",
    ]
    if pay_id:
        lines.append(f"{pay_label}: {pay_id}")
    if merchant_order_id:
        lines.append(f"Заказ мерчанта: {merchant_order_id}")
    lines.extend(
        [
            f"Мерчант: {merchant or '—'}",
            f"Трейдер: {trader or '—'}",
            f"Было: {_money(amount)} {currency}".rstrip(),
            f"Стало: {_money(new_amount)} {currency}".rstrip(),
        ]
    )
    if receipt:
        lines.append(f"Чек: {receipt}")
    lines.append("")
    lines.append("Подтвердить — провести новую сумму. Отклонить — отменить заявку.")
    return "\n".join(lines)


def queue_recalc_confirmation(order, side: str) -> None:
    order_id = str(order.id)

    def _send() -> None:
        try:
            notify_recalc_confirmation(side, order_id)
        except Exception:
            logger.exception("recalc confirm notify failed order=%s", order_id)

    transaction.on_commit(_send)


def notify_recalc_confirmation(side: str, order_id: str) -> bool:
    order = _load(side, order_id)
    if order is None:
        return False
    text = format_recalc_prompt(**_prompt_kwargs(order, side))
    keyboard = {
        "inline_keyboard": [[
            {"text": "Подтвердить", "callback_data": f"{side}:y:{order_id}"},
            {"text": "Отклонить", "callback_data": f"{side}:n:{order_id}"},
        ]]
    }
    return _send_message(text, keyboard)


def apply_recalc_decision(side: str, order_id: str, approve: bool) -> str:
    try:
        with transaction.atomic():
            order = _locked(side, order_id)
            if order is None:
                return "Заявка не найдена"
            status_name = order.status.name if order.status_id else ""
            if status_name != "Recalculation":
                return f"Уже обработано. Статус: {status_name or '—'}"
            new_amount = Decimal(order.recalculated_amount or 0)
            if approve:
                if new_amount <= 0:
                    return "Сумма перерасчёта не задана"
                if side == "rin":
                    order.support_recalculate(new_amount)
                else:
                    order.recalculate(new_amount)
                return f"Подтверждено. Новая сумма {_money(new_amount)}"
            if side == "rin":
                order.cancel_by_support()
            else:
                order.cancel_support()
            return "Отклонено. Заявка отменена, заморозка снята"
    except ValidationError as exc:
        return f"Не удалось: {_validation_text(exc)}"


def _load(side: str, order_id: str):
    if side == "rin":
        from trade.models import InOrder

        return (
            InOrder.objects.select_related(
                "status",
                "solution__merchant__user",
                "solution__payment_system__currency",
                "payment_details__group__trader__user",
            )
            .filter(id=order_id)
            .first()
        )
    from trade.models import OutOrder

    return (
        OutOrder.objects.select_related(
            "status",
            "solution__merchant__user",
            "solution__payment_system__currency",
            "payment_details__group__trader__user",
        )
        .filter(id=order_id)
        .first()
    )


def _locked(side: str, order_id: str):
    if side == "rin":
        from trade.models import InOrder

        return InOrder.objects.select_for_update().filter(id=order_id).first()
    from trade.models import OutOrder

    return OutOrder.objects.select_for_update().filter(id=order_id).first()


def _prompt_kwargs(order, side: str) -> dict:
    merchant = ""
    trader = ""
    currency = ""
    pay_id = ""
    solution = getattr(order, "solution", None)
    if solution is not None and solution.merchant_id and getattr(solution.merchant, "user", None):
        merchant = solution.merchant.user.username
    payment_system = getattr(solution, "payment_system", None) if solution is not None else None
    if payment_system is not None and payment_system.currency_id:
        currency = payment_system.currency.symbol or ""
    details = getattr(order, "payment_details", None)
    if details is not None and details.group_id and details.group.trader_id:
        trader = details.group.trader.user.username
    if side == "rin":
        pay = order.pay_in.order_by("-created_at").first()
    else:
        pay = order.pay_out.order_by("-created_at").first() if hasattr(order, "pay_out") else None
    if pay is not None:
        pay_id = str(pay.id)
    receipt = order.pic if str(getattr(order, "pic", "") or "").startswith("http") else ""
    return {
        "side": side,
        "order_id": str(order.id),
        "merchant": merchant,
        "trader": trader,
        "currency": currency,
        "amount": order.amount,
        "new_amount": order.recalculated_amount,
        "merchant_order_id": order.merchant_order_id or "",
        "pay_id": pay_id,
        "receipt": receipt,
    }


def _money(value) -> str:
    try:
        return f"{Decimal(value):.2f}"
    except Exception:
        return str(value)


def _validation_text(exc: ValidationError) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        parts = []
        for item in detail.values():
            if isinstance(item, (list, tuple)):
                parts.extend(str(piece) for piece in item)
            else:
                parts.append(str(item))
        return "; ".join(parts)[:300]
    return str(exc)[:300]


def _send_message(text: str, reply_markup: dict | None) -> bool:
    token = _bot_token()
    chat_id = _chat_id()
    if not token or not chat_id or not text:
        logger.info("recalc confirm skipped: admin bot is not configured")
        return False
    body = {"chat_id": chat_id, "text": text[:4000]}
    if reply_markup:
        body["reply_markup"] = reply_markup
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=body,
            timeout=15,
        )
        payload = response.json()
    except Exception as exc:
        logger.error("recalc confirm telegram failed: %s", exc)
        return False
    if not payload.get("ok"):
        logger.error("recalc confirm telegram rejected: %s", payload)
        return False
    return True


def edit_admin_message(chat_id: str, message_id: int, text: str) -> None:
    token = _bot_token()
    if not token or not chat_id or not message_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text[:4000]},
            timeout=15,
        )
    except Exception:
        logger.exception("recalc confirm edit failed")


def answer_callback(callback_id: str, text: str) -> None:
    token = _bot_token()
    if not token or not callback_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": (text or "")[:180], "show_alert": False},
            timeout=15,
        )
    except Exception:
        logger.exception("recalc confirm callback answer failed")
