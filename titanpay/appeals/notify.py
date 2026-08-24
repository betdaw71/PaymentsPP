from __future__ import annotations

import logging

from django.db.models import Q

from appeals.models import PayInAppeal, PayInAppealStatus
from appeals.telegram_out import notify_merchant_appeal_message

logger = logging.getLogger(__name__)


def _pending_appeals_for_order(order):
    if order is None:
        return PayInAppeal.objects.none()
    return PayInAppeal.objects.filter(
        status=PayInAppealStatus.SENT_TO_PROVIDER,
    ).filter(Q(in_order=order) | Q(pay_in__order=order))


def resolve_pending_appeals_for_order(order, *, approved: bool) -> None:
    for appeal in _pending_appeals_for_order(order):
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
