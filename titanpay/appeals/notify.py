from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from appeals.models import PayInAppeal, PayInAppealStatus
from appeals.telegram_out import notify_merchant_appeal_message, send_text_to_provider_chat

logger = logging.getLogger(__name__)

NUDGE_1H = timedelta(hours=1)
NUDGE_3H = timedelta(hours=3)
PROVIDER_NUDGE_TEXT = "?"


def _pending_appeals_for_order(order):
    if order is None:
        return PayInAppeal.objects.none()

    from payments.models import PayIn

    pay_in_ids = PayIn.objects.filter(order_id=order.pk).values_list("id", flat=True)
    return PayInAppeal.objects.filter(
        status=PayInAppealStatus.SENT_TO_PROVIDER,
    ).filter(
        Q(in_order_id=order.pk)
        | Q(pay_in_id__in=pay_in_ids)
        | Q(pay_in__order_id=order.pk)
    )


def resolve_pending_appeals_for_order(order, *, approved: bool) -> None:
    appeals = list(_pending_appeals_for_order(order))
    if not appeals:
        logger.warning(
            "no pending appeals for order=%s approved=%s",
            getattr(order, "id", None),
            approved,
        )
        return

    for appeal in appeals:
        appeal.status = PayInAppealStatus.APPROVED if approved else PayInAppealStatus.REJECTED
        appeal.save(update_fields=["status"])
        try:
            notify_merchant_appeal_message(
                chat_id=appeal.source_telegram_chat_id,
                message_id=appeal.source_telegram_message_id,
                approved=approved,
            )
        except Exception:
            logger.exception("appeal notify failed appeal_id=%s", appeal.id)


def resolve_pending_appeals_for_pay_in(pay_in, *, approved: bool) -> None:
    order = getattr(pay_in, "order", None)
    if order is not None:
        resolve_pending_appeals_for_order(order, approved=approved)
        return
    for appeal in PayInAppeal.objects.filter(pay_in=pay_in, status=PayInAppealStatus.SENT_TO_PROVIDER):
        appeal.status = PayInAppealStatus.APPROVED if approved else PayInAppealStatus.REJECTED
        appeal.save(update_fields=["status"])
        try:
            notify_merchant_appeal_message(
                chat_id=appeal.source_telegram_chat_id,
                message_id=appeal.source_telegram_message_id,
                approved=approved,
            )
        except Exception:
            logger.exception("appeal notify failed appeal_id=%s", appeal.id)


def _send_provider_nudge(appeal: PayInAppeal) -> bool:
    if not appeal.provider_chat_id:
        return False
    sent = send_text_to_provider_chat(
        chat_id=appeal.provider_chat_id,
        text=PROVIDER_NUDGE_TEXT,
        reply_to_message_id=appeal.provider_message_id,
    )
    if not sent.ok:
        logger.warning(
            "provider nudge failed appeal_id=%s chat_id=%s: %s",
            appeal.id,
            appeal.provider_chat_id,
            sent.error,
        )
        return False
    return True


def nudge_unanswered_provider_appeals() -> int:
    """Send '?' in the provider chat 1h and 3h after an appeal was forwarded with no answer."""
    now = timezone.now()
    sent_count = 0
    pending = PayInAppeal.objects.filter(
        status=PayInAppealStatus.SENT_TO_PROVIDER,
        provider_chat_id__isnull=False,
    )
    for appeal in pending.iterator():
        age = now - appeal.created_at
        updates: list[str] = []
        if age >= NUDGE_1H and appeal.provider_nudge_1h_at is None:
            if _send_provider_nudge(appeal):
                appeal.provider_nudge_1h_at = now
                updates.append("provider_nudge_1h_at")
        if age >= NUDGE_3H and appeal.provider_nudge_3h_at is None:
            if _send_provider_nudge(appeal):
                appeal.provider_nudge_3h_at = now
                updates.append("provider_nudge_3h_at")
        if updates:
            appeal.save(update_fields=updates)
            sent_count += 1
    if sent_count:
        logger.info("provider appeal nudges sent for %s appeal(s)", sent_count)
    return sent_count
