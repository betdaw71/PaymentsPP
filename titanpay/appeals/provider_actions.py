"""Кнопки под апелляцией в чате провайдера: успех, отказ, запрос информации."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from django.db import transaction

from appeals.models import PayInAppeal, PayInAppealStatus
from appeals.telegram_out import (
    clear_provider_keyboard,
    edit_provider_appeal_message,
    send_merchant_notice,
)

logger = logging.getLogger(__name__)

REJECT_PROMPT = "ответом на это сообщение укажите причину отклонения"
DEFAULT_REJECT_REASON = ""  # отказ без причины — мерчу уходит только «Статус: отклонено»
_ACTIONS = {"y": "confirm", "n": "reject", "i": "info"}
_REJECTABLE = (
    PayInAppealStatus.SENT_TO_PROVIDER,
    PayInAppealStatus.AWAITING_REJECT_REASON,
)


@dataclass
class ActionResult:
    ok: bool
    message: str
    handled: bool = True


def provider_keyboard(appeal_id) -> dict:
    token = str(appeal_id)
    return {
        "inline_keyboard": [
            [{"text": "Подтвердить", "callback_data": f"ap:y:{token}"}],
            [{"text": "Отклонить", "callback_data": f"ap:n:{token}"}],
            [{"text": "Запросить доп информацию", "callback_data": f"ap:i:{token}"}],
        ]
    }


def parse_provider_callback(data: str) -> tuple[str, uuid.UUID] | None:
    parts = (data or "").strip().split(":")
    if len(parts) != 3 or parts[0] != "ap" or parts[1] not in _ACTIONS:
        return None
    try:
        appeal_id = uuid.UUID(parts[2])
    except ValueError:
        return None
    return _ACTIONS[parts[1]], appeal_id


def merchant_order_label(pay_in) -> str:
    label = (getattr(pay_in, "merchant_order_id", None) or "").strip()
    if label:
        return label
    return str(getattr(pay_in, "id", "") or "")


def merchant_reject_text(pay_in, reason: str = "") -> str:
    lines = [merchant_order_label(pay_in), "Статус: отклонено"]
    cleaned = (reason or "").strip()
    if cleaned:
        lines.append(f"Причина: {cleaned}")
    return "\n".join(lines)


def merchant_info_text(pay_in) -> str:
    return f"Запрос доп информации\n{merchant_order_label(pay_in)}"


def restored_provider_text(original: str, reason: str) -> str:
    original = (original or "").strip()
    reason = (reason or "").strip()
    if reason:
        suffix = f"Причина отклонения: {reason}"
    else:
        suffix = "Отклонено (без указания причины)"
    if original:
        body = f"{original}\n\n{suffix}"
    else:
        body = suffix
    return body[:1024]


def _order_for_appeal(appeal: PayInAppeal):
    if appeal.in_order_id:
        return appeal.in_order
    pay_in = appeal.pay_in
    return getattr(pay_in, "order", None)


def _notify_merchant(appeal: PayInAppeal, text: str) -> None:
    send_merchant_notice(
        chat_id=appeal.source_telegram_chat_id,
        text=text,
        reply_to_message_id=appeal.source_telegram_message_id,
    )


def apply_provider_callback(callback_data: str) -> ActionResult:
    parsed = parse_provider_callback(callback_data)
    if parsed is None:
        return ActionResult(ok=False, message="Неизвестная кнопка", handled=False)
    action, appeal_id = parsed
    if action == "confirm":
        return _confirm(appeal_id)
    if action == "reject":
        return reject_appeal(appeal_id, reason=DEFAULT_REJECT_REASON)
    return _request_info(appeal_id)


def _confirm(appeal_id: uuid.UUID) -> ActionResult:
    chat_id = None
    message_id = None
    try:
        with transaction.atomic():
            appeal = (
                PayInAppeal.objects.select_for_update()
                .select_related("in_order", "pay_in")
                .filter(pk=appeal_id)
                .first()
            )
            if appeal is None:
                return ActionResult(ok=False, message="Апелляция не найдена")
            if appeal.status == PayInAppealStatus.APPROVED:
                return ActionResult(ok=True, message="Уже подтверждено")
            if appeal.status != PayInAppealStatus.SENT_TO_PROVIDER:
                return ActionResult(ok=False, message="Апелляция уже обработана")
            order = _order_for_appeal(appeal)
            if order is None or order.status_id is None:
                return ActionResult(ok=False, message="Заявка не найдена")
            status_name = order.status.name
            chat_id = appeal.provider_chat_id
            message_id = appeal.provider_message_id
            if status_name == "Completed":
                appeal.status = PayInAppealStatus.APPROVED
                appeal.save(update_fields=["status"])
            elif status_name == "Arbitrage":
                # complete() сам закроет апелляцию и напишет мерчанту «Успех».
                order.complete_after_arbitrage()
            else:
                return ActionResult(ok=False, message=f"Нельзя подтвердить из статуса {status_name}")
    except Exception:
        logger.exception("appeal confirm failed appeal_id=%s", appeal_id)
        return ActionResult(ok=False, message="Не удалось перевести заявку в успех")

    if chat_id and message_id:
        clear_provider_keyboard(chat_id=chat_id, message_id=message_id)
    return ActionResult(ok=True, message="Заявка переведена в успех")


def reject_appeal(appeal_id: uuid.UUID, *, reason: str = DEFAULT_REJECT_REASON) -> ActionResult:
    """Сразу отклонить апелляцию и уведомить мерчанта (причина опциональна)."""
    reason = (reason or "").strip()
    merchant_text = ""
    edit_args = None
    try:
        with transaction.atomic():
            appeal = (
                PayInAppeal.objects.select_for_update()
                .select_related(
                    "in_order",
                    "in_order__status",
                    "pay_in",
                    "pay_in__order",
                    "pay_in__order__status",
                )
                .filter(pk=appeal_id)
                .first()
            )
            if appeal is None:
                return ActionResult(ok=False, message="Апелляция не найдена")
            if appeal.status == PayInAppealStatus.REJECTED:
                return ActionResult(ok=True, message="Уже отклонено")
            if appeal.status not in _REJECTABLE:
                return ActionResult(ok=False, message="Апелляция уже обработана")
            appeal.status = PayInAppealStatus.REJECTED
            appeal.provider_reject_reason = reason[:2000]
            appeal.save(update_fields=["status", "provider_reject_reason"])
            order = _order_for_appeal(appeal)
            if order is not None and order.status_id and order.status.name == "Arbitrage":
                try:
                    order.cancel_by_trader("no-pay")
                except Exception:
                    logger.exception("appeal cancel_by_trader failed appeal_id=%s", appeal.id)
            merchant_text = merchant_reject_text(appeal.pay_in, reason)
            edit_args = (
                appeal.provider_chat_id,
                appeal.provider_message_id,
                restored_provider_text(appeal.provider_original_text, reason),
                appeal.provider_has_media,
                appeal.source_telegram_chat_id,
                appeal.source_telegram_message_id,
            )
    except Exception:
        logger.exception("appeal reject failed appeal_id=%s", appeal_id)
        return ActionResult(ok=False, message="Не удалось отклонить заявку")

    if edit_args is not None:
        chat, message_id, caption, has_media, merchant_chat, merchant_message = edit_args
        if chat and message_id:
            edit_provider_appeal_message(
                chat_id=chat,
                message_id=message_id,
                text=caption,
                has_media=has_media,
                remove_keyboard=True,
            )
        send_merchant_notice(
            chat_id=merchant_chat,
            text=merchant_text,
            reply_to_message_id=merchant_message,
        )
    return ActionResult(
        ok=True,
        message="Заявка отклонена" if not reason else "Причина отправлена мерчанту",
    )


def _request_info(appeal_id: uuid.UUID) -> ActionResult:
    appeal = (
        PayInAppeal.objects.select_related("pay_in")
        .filter(pk=appeal_id, status=PayInAppealStatus.SENT_TO_PROVIDER)
        .first()
    )
    if appeal is None:
        return ActionResult(ok=False, message="Апелляция уже обработана")
    _notify_merchant(appeal, merchant_info_text(appeal.pay_in))
    return ActionResult(ok=True, message="Запрос отправлен мерчанту")


def apply_provider_reject_reply(*, chat_id: int, reply_to_message_id: int, text: str) -> ActionResult:
    """Опциональный reply с причиной (legacy awaiting_reject_reason). Пустой текст = отказ без причины."""
    reason = (text or "").strip()
    with transaction.atomic():
        appeal = (
            PayInAppeal.objects.select_for_update()
            .filter(
                provider_chat_id=chat_id,
                provider_message_id=reply_to_message_id,
                status=PayInAppealStatus.AWAITING_REJECT_REASON,
            )
            .first()
        )
        if appeal is None:
            return ActionResult(ok=True, message="", handled=False)
        appeal_id = appeal.id
    return reject_appeal(appeal_id, reason=reason)
