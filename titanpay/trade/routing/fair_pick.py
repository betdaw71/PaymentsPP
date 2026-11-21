"""Выбор карты/реквизита с наименьшей нагрузкой вместо чистого random."""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

_OPEN_STATUSES = ("New", "Money sent by user", "Arbitrage", "Recalculation")


def _pick_window_hours() -> int:
    try:
        from trade.routing.human_fair import fair_window_hours

        return fair_window_hours()
    except Exception:
        return 24


def pick_least_loaded_detail(available_details: QuerySet):
    """
    Среди свободных PaymentDetails выбираем наименее загруженный:
      1) меньше открытых заявок (любая сумма)
      2) меньше выдач за окно HUMAN_ROUTING_WINDOW_HOURS
      3) random tie-break
    """
    if available_details is None:
        return None
    since = timezone.now() - timedelta(hours=_pick_window_hours())
    ranked = available_details.annotate(
        open_cnt=Count(
            "inorders",
            filter=Q(inorders__status__name__in=_OPEN_STATUSES),
            distinct=True,
        ),
        recent_cnt=Count(
            "inorders",
            filter=Q(inorders__creation_date__gte=since),
            distinct=True,
        ),
    ).order_by("open_cnt", "recent_cnt", "?")
    return ranked.first()
