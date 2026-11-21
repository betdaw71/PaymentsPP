"""Равномерная выдача между живыми трейдерами и реквизитами.

Проблема: сортировка по current_volume + сброс volume на Expired
даёт весь поток трейдеру/карте с плохой конверсией (fail-loop).

Решение: приоритет — число выдач и открытых заявок за окно, не «деньги в периоде».
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

_OPEN_STATUSES = ("New", "Money sent by user", "Arbitrage", "Recalculation")


def fair_routing_enabled() -> bool:
    raw = getattr(settings, "HUMAN_ROUTING_FAIR", True)
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(raw)


def fair_window_hours() -> int:
    try:
        h = int(getattr(settings, "HUMAN_ROUTING_WINDOW_HOURS", 6) or 6)
    except (TypeError, ValueError):
        h = 6
    return max(1, min(48, h))


def max_open_per_detail() -> int:
    """0 = выключено. Иначе карта с ≥N открытыми (любая сумма) не берётся."""
    try:
        n = int(getattr(settings, "HUMAN_ROUTING_MAX_OPEN_PER_DETAIL", 2) or 2)
    except (TypeError, ValueError):
        n = 2
    return max(0, min(50, n))


def fair_share_lead() -> int:
    """
    Soft-skip: если у группы выдач за окно ≥ min(peers) + lead
    и есть другой живой кандидат — пропустить (ровный шаринг).
    0 = выключено.
    """
    try:
        n = int(getattr(settings, "HUMAN_ROUTING_FAIR_SHARE_LEAD", 3) or 3)
    except (TypeError, ValueError):
        n = 3
    return max(0, min(100, n))


def fetch_group_load_stats(group_ids, *, window_hours: int | None = None) -> dict[str, dict]:
    """
    {group_id_str: {recent: int, open: int}}
    recent — выдачи за окно; open — сейчас открытые.
    """
    ids = [gid for gid in group_ids if gid is not None]
    if not ids:
        return {}
    hours = fair_window_hours() if window_hours is None else max(1, min(48, int(window_hours)))
    since = timezone.now() - timedelta(hours=hours)
    out = {str(gid): {"recent": 0, "open": 0} for gid in ids}
    try:
        from trade.models import InOrder

        for row in (
            InOrder.objects.filter(
                payment_details__group_id__in=ids,
                creation_date__gte=since,
            )
            .values("payment_details__group_id")
            .annotate(n=Count("id"))
        ):
            gid = row["payment_details__group_id"]
            if gid is not None:
                out[str(gid)]["recent"] = int(row["n"] or 0)

        for row in (
            InOrder.objects.filter(
                payment_details__group_id__in=ids,
                status__name__in=_OPEN_STATUSES,
            )
            .values("payment_details__group_id")
            .annotate(n=Count("id", distinct=True))
        ):
            gid = row["payment_details__group_id"]
            if gid is not None:
                out[str(gid)]["open"] = int(row["n"] or 0)
    except Exception:
        logger.exception("human_fair load stats failed")
    return out


def sort_human_groups(groups, *, load_stats: dict | None = None):
    """
    Меньше выдач за окно → раньше; затем меньше открытых; затем volume; username.
    """
    groups = list(groups)
    if not groups:
        return groups
    if load_stats is None:
        load_stats = fetch_group_load_stats([getattr(g, "id", None) for g in groups])

    def key(g):
        st = load_stats.get(str(getattr(g, "id", "")), {}) or {}
        recent = int(st.get("recent") or 0)
        open_n = int(st.get("open") or 0)
        vol = getattr(g, "current_volume", None) or Decimal(0)
        uname = ""
        try:
            uname = (g.trader.user.username or "").lower()
        except Exception:
            uname = str(getattr(g, "id", ""))
        return (recent, open_n, vol, uname)

    return sorted(groups, key=key)


def should_skip_fair_share(
    group,
    *,
    peer_groups: list,
    load_stats: dict,
    remaining_peers: list,
) -> str | None:
    """
    Пропуск группы, если она заметно впереди по выдачам, а есть кто ещё.
    Не срабатывает, если это последний живой кандидат.
    """
    lead = fair_share_lead()
    if lead <= 0 or not remaining_peers:
        return None
    mine = int((load_stats.get(str(group.id), {}) or {}).get("recent") or 0)
    peer_recents = [
        int((load_stats.get(str(g.id), {}) or {}).get("recent") or 0)
        for g in remaining_peers
    ]
    if not peer_recents:
        return None
    floor = min(peer_recents)
    if mine >= floor + lead:
        return "fair_share"
    return None


def exclude_overloaded_details(available_details, *, max_open: int | None = None):
    """Убрать реквизиты с ≥ max_open открытыми заявками (любая сумма)."""
    if available_details is None:
        return available_details
    limit = max_open_per_detail() if max_open is None else max_open
    if limit <= 0:
        return available_details
    try:
        return available_details.annotate(
            _fair_open=Count(
                "inorders",
                filter=Q(inorders__status__name__in=_OPEN_STATUSES),
                distinct=True,
            )
        ).filter(_fair_open__lt=limit)
    except Exception:
        logger.exception("exclude_overloaded_details failed")
        return available_details
