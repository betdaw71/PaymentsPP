"""Интервал сумм/времени между заявками на группе реквизита (живые трейдеры)."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

ACTIVE_IN_STATUSES = ("New", "Money sent by user")


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def group_skip_reason_for_deal_spacing(group, amount) -> str | None:
    """
    Почему группу нельзя взять сейчас, или None.

    amount_diff: среди активных заявок группы нет суммы с |Δ| < amount_diff.
    deal_interval_sec: с последней выдачи (creation_date) прошло ≥ N секунд.
    0 / None = правило выключено.
    """
    diff = _dec(getattr(group, "amount_diff", 0) or 0)
    interval = int(getattr(group, "deal_interval_sec", 0) or 0)

    if diff <= 0 and interval <= 0:
        return None

    from trade.models import InOrder

    if interval > 0:
        last_issued = (
            InOrder.objects.filter(payment_details__group_id=group.id)
            .exclude(payment_details__isnull=True)
            .order_by("-creation_date")
            .values_list("creation_date", flat=True)
            .first()
        )
        if last_issued is not None and timezone.now() - last_issued < timedelta(seconds=interval):
            return "deal_interval"

    if diff > 0:
        amt = _dec(amount)
        active_amounts = InOrder.objects.filter(
            payment_details__group_id=group.id,
            status__name__in=ACTIVE_IN_STATUSES,
        ).values_list("amount", flat=True)
        for other in active_amounts:
            if abs(amt - _dec(other)) < diff:
                return "amount_diff"

    return None
