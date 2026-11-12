"""Операционный дашборд Head Support: KPI, объёмы по дням, конверсия, PnL, разбивки."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce, TruncDay

from basics.cash_register import (
    DEC,
    MSK,
    ZERO,
    _psp_effective_usd,
    melbet_fiat_merchant_fee_usd_expr,
    money,
    money_str,
)

Q2 = Decimal("0.01")


def _parse_day(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def resolve_period(
    *,
    preset: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime, str]:
    """Вернуть [start, end) в Europe/Moscow и нормализованный preset."""
    current = (now or datetime.now(MSK)).astimezone(MSK)
    today = current.date()
    kind = (preset or "today").strip().lower()

    if kind == "custom":
        d0 = _parse_day(date_from) or today
        d1 = _parse_day(date_to) or d0
        if d1 < d0:
            d0, d1 = d1, d0
        start = datetime.combine(d0, time.min, tzinfo=MSK)
        end = datetime.combine(d1 + timedelta(days=1), time.min, tzinfo=MSK)
        return start, end, "custom"

    if kind == "yesterday":
        day = today - timedelta(days=1)
        start = datetime.combine(day, time.min, tzinfo=MSK)
        end = start + timedelta(days=1)
        return start, end, "yesterday"

    if kind in {"7d", "7days", "week"}:
        start = datetime.combine(today - timedelta(days=6), time.min, tzinfo=MSK)
        end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=MSK)
        return start, end, "7d"

    if kind in {"month", "mtd"}:
        start = datetime(today.year, today.month, 1, 0, 0, 0, tzinfo=MSK)
        end = current
        # include today partially: end = now
        return start, end, "month"

    # today
    start = datetime.combine(today, time.min, tzinfo=MSK)
    end = start + timedelta(days=1)
    return start, end, "today"


def _pct(part: int | Decimal, whole: int | Decimal) -> str:
    if not whole or Decimal(str(whole)) <= 0:
        return "0.00"
    return f"{(Decimal(str(part)) * Decimal('100') / Decimal(str(whole))).quantize(Q2):.2f}"


def _apply_order_filters(qs, *, merchant: str, psp: str, ps: str):
    if merchant:
        qs = qs.filter(solution__merchant__user__username=merchant)
    if ps:
        qs = qs.filter(solution__payment_system__name=ps)
    if psp:
        qs = qs.filter(payment_details__group__trader__user__username=psp)
    return qs


def snapshot(
    *,
    preset: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    merchant: str | None = None,
    psp: str | None = None,
    ps: str | None = None,
    direction: str | None = None,
    now: datetime | None = None,
) -> dict:
    from basics.models import PlatformExpense
    from merchant.models import Merchant
    from payments.models import PayIn
    from trade.models import InOrder, OutOrder

    start, end, kind = resolve_period(preset=preset, date_from=date_from, date_to=date_to, now=now)
    merchant = (merchant or "").strip()
    psp = (psp or "").strip()
    ps = (ps or "").strip()
    direction = (direction or "both").strip().lower()
    if direction not in {"in", "out", "both"}:
        direction = "both"

    in_qs = InOrder.objects.filter(
        status__name="Completed",
        completion_date__gte=start,
        completion_date__lt=end,
    )
    out_qs = OutOrder.objects.filter(
        status__name="Completed",
        completion_date__gte=start,
        completion_date__lt=end,
    )
    in_qs = _apply_order_filters(in_qs, merchant=merchant, psp=psp, ps=ps)
    out_qs = _apply_order_filters(out_qs, merchant=merchant, psp=psp, ps=ps)
    if direction == "in":
        out_qs = out_qs.none()
    elif direction == "out":
        in_qs = in_qs.none()

    mdr = melbet_fiat_merchant_fee_usd_expr()

    # --- PnL ---
    in_agg = in_qs.aggregate(
        merchant_fee=Coalesce(Sum(mdr), Value(ZERO, output_field=DEC)),
        trader_fee=Coalesce(Sum("trader_fee"), Value(ZERO, output_field=DEC)),
        agent_fee=Coalesce(Sum("agent_fee"), Value(ZERO, output_field=DEC)),
        fx_spread=Coalesce(
            Sum(ExpressionWrapper(_psp_effective_usd() - F("usd_amount"), output_field=DEC)),
            Value(ZERO, output_field=DEC),
        ),
        turnover=Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)),
        count=Count("id"),
    )
    out_agg = out_qs.aggregate(
        merchant_fee=Coalesce(Sum(mdr), Value(ZERO, output_field=DEC)),
        trader_fee=Coalesce(Sum("trader_fee"), Value(ZERO, output_field=DEC)),
        turnover=Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)),
        count=Count("id"),
    )

    include_expenses = not merchant and not psp and not ps and direction == "both"
    if include_expenses:
        exp = PlatformExpense.objects.filter(created_at__gte=start, created_at__lt=end).aggregate(
            total=Coalesce(Sum("amount"), Value(ZERO, output_field=DEC)),
            count=Count("id"),
        )
        expense_total = money(exp["total"])
        expense_count = exp["count"] or 0
    else:
        expense_total = ZERO
        expense_count = 0

    payin_mdr = money(in_agg["merchant_fee"])
    payin_fx = money(in_agg["fx_spread"])
    payin_trader = money(in_agg["trader_fee"])
    agent = money(in_agg["agent_fee"])
    payout_mdr = money(out_agg["merchant_fee"])
    payout_trader = money(out_agg["trader_fee"])
    turnover = money(in_agg["turnover"]) + money(out_agg["turnover"])
    net = money(
        payin_mdr + payin_fx + payout_mdr - payin_trader - payout_trader - agent - expense_total
    )

    # --- Daily volumes ---
    daily_map: dict[str, dict] = {}
    if direction in {"in", "both"}:
        for row in (
            in_qs.annotate(day=TruncDay("completion_date", tzinfo=MSK))
            .values("day")
            .annotate(usd=Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)))
            .order_by("day")
        ):
            if not row["day"]:
                continue
            key = row["day"].astimezone(MSK).date().isoformat()
            cell = daily_map.setdefault(key, {"date": key, "usd_in": ZERO, "usd_out": ZERO})
            cell["usd_in"] += money(row["usd"])
    if direction in {"out", "both"}:
        for row in (
            out_qs.annotate(day=TruncDay("completion_date", tzinfo=MSK))
            .values("day")
            .annotate(usd=Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)))
            .order_by("day")
        ):
            if not row["day"]:
                continue
            key = row["day"].astimezone(MSK).date().isoformat()
            cell = daily_map.setdefault(key, {"date": key, "usd_in": ZERO, "usd_out": ZERO})
            cell["usd_out"] += money(row["usd"])

    # Fill empty days in range for chart continuity
    day_cursor = start.astimezone(MSK).date()
    end_day = (end.astimezone(MSK) - timedelta(seconds=1)).date()
    daily = []
    while day_cursor <= end_day:
        key = day_cursor.isoformat()
        cell = daily_map.get(key, {"date": key, "usd_in": ZERO, "usd_out": ZERO})
        usd_in = money(cell["usd_in"])
        usd_out = money(cell["usd_out"])
        daily.append(
            {
                "date": key,
                "usd_in": money_str(usd_in),
                "usd_out": money_str(usd_out),
                "usd_total": money_str(usd_in + usd_out),
            }
        )
        day_cursor += timedelta(days=1)

    # --- Conversion (pay-in cohort by created_at) ---
    payins = PayIn.objects.filter(created_at__gte=start, created_at__lt=end)
    if merchant:
        payins = payins.filter(merchant__user__username=merchant)
    if ps:
        payins = payins.filter(payment_system__name=ps)
    if psp:
        payins = payins.filter(order__payment_details__group__trader__user__username=psp)
    if direction == "out":
        created = declined = issued = success = 0
    else:
        created = payins.count()
        declined = payins.filter(status__name="Declined").count()
        issued = created - declined
        success = payins.filter(status__name="Success").count()

    # --- Breakdowns ---
    def _group_rows(qs, *fields, include_fx: bool = True):
        ann = {
            "n": Count("id"),
            "usd": Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)),
            "mdr": Coalesce(Sum(mdr), Value(ZERO, output_field=DEC)),
            "trader": Coalesce(Sum("trader_fee"), Value(ZERO, output_field=DEC)),
            "agent": Coalesce(Sum("agent_fee"), Value(ZERO, output_field=DEC)),
        }
        if include_fx:
            ann["fx"] = Coalesce(
                Sum(ExpressionWrapper(_psp_effective_usd() - F("usd_amount"), output_field=DEC)),
                Value(ZERO, output_field=DEC),
            )
        return list(qs.values(*fields).annotate(**ann))

    by_merchant_map: dict[str, dict] = {}
    if direction in {"in", "both"}:
        for row in _group_rows(in_qs, "solution__merchant__user__username"):
            name = row["solution__merchant__user__username"] or "(none)"
            cell = by_merchant_map.setdefault(
                name, {"name": name, "n": 0, "usd": ZERO, "mdr": ZERO, "fx": ZERO, "trader": ZERO, "agent": ZERO}
            )
            cell["n"] += row["n"] or 0
            cell["usd"] += money(row["usd"])
            cell["mdr"] += money(row["mdr"])
            cell["fx"] += money(row.get("fx"))
            cell["trader"] += money(row["trader"])
            cell["agent"] += money(row["agent"])
    if direction in {"out", "both"}:
        for row in _group_rows(out_qs, "solution__merchant__user__username", include_fx=False):
            name = row["solution__merchant__user__username"] or "(none)"
            cell = by_merchant_map.setdefault(
                name, {"name": name, "n": 0, "usd": ZERO, "mdr": ZERO, "fx": ZERO, "trader": ZERO, "agent": ZERO}
            )
            cell["n"] += row["n"] or 0
            cell["usd"] += money(row["usd"])
            cell["mdr"] += money(row["mdr"])
            cell["trader"] += money(row["trader"])

    by_merchant = []
    for cell in by_merchant_map.values():
        usd = money(cell["usd"])
        net_row = money(cell["mdr"] + cell["fx"] - cell["trader"] - cell["agent"])
        by_merchant.append(
            {
                "name": cell["name"],
                "n": cell["n"],
                "usd": money_str(usd),
                "mdr": money_str(cell["mdr"]),
                "fx": money_str(cell["fx"]),
                "trader_fee": money_str(cell["trader"]),
                "agent_fee": money_str(cell["agent"]),
                "net": money_str(net_row),
                "margin_pct": _pct(net_row, usd) if usd > 0 else "0.00",
            }
        )
    by_merchant.sort(key=lambda r: Decimal(r["usd"]), reverse=True)

    by_psp_map: dict[str, dict] = {}
    if direction in {"in", "both"}:
        for row in _group_rows(in_qs, "payment_details__group__trader__user__username"):
            name = row["payment_details__group__trader__user__username"] or "(none)"
            cell = by_psp_map.setdefault(
                name, {"name": name, "n": 0, "usd": ZERO, "mdr": ZERO, "fx": ZERO, "trader": ZERO, "agent": ZERO}
            )
            cell["n"] += row["n"] or 0
            cell["usd"] += money(row["usd"])
            cell["mdr"] += money(row["mdr"])
            cell["fx"] += money(row.get("fx"))
            cell["trader"] += money(row["trader"])
            cell["agent"] += money(row["agent"])
    if direction in {"out", "both"}:
        for row in _group_rows(out_qs, "payment_details__group__trader__user__username", include_fx=False):
            name = row["payment_details__group__trader__user__username"] or "(none)"
            cell = by_psp_map.setdefault(
                name, {"name": name, "n": 0, "usd": ZERO, "mdr": ZERO, "fx": ZERO, "trader": ZERO, "agent": ZERO}
            )
            cell["n"] += row["n"] or 0
            cell["usd"] += money(row["usd"])
            cell["mdr"] += money(row["mdr"])
            cell["trader"] += money(row["trader"])

    by_psp = []
    for cell in by_psp_map.values():
        usd = money(cell["usd"])
        fx = money(cell["fx"])
        trader = money(cell["trader"])
        net_row = money(cell["mdr"] + fx - trader - cell["agent"])
        eff = money(trader - fx)
        by_psp.append(
            {
                "name": cell["name"],
                "n": cell["n"],
                "usd": money_str(usd),
                "mdr": money_str(cell["mdr"]),
                "fx": money_str(fx),
                "trader_fee": money_str(trader),
                "agent_fee": money_str(cell["agent"]),
                "net": money_str(net_row),
                "margin_pct": _pct(net_row, usd) if usd > 0 else "0.00",
                "eff_psp_cost_pct": _pct(eff, usd) if usd > 0 else "0.00",
            }
        )
    by_psp.sort(key=lambda r: Decimal(r["usd"]), reverse=True)

    # Filter options (active merchants / PSPs with traffic)
    merchant_names = sorted(
        Merchant.objects.filter(user__isnull=False).values_list("user__username", flat=True).distinct()
    )
    psp_names = sorted(
        {
            *(r["name"] for r in by_psp if r["name"] != "(none)"),
            *InOrder.objects.filter(
                completion_date__gte=start - timedelta(days=30),
                payment_details__group__trader__user__isnull=False,
            )
            .values_list("payment_details__group__trader__user__username", flat=True)
            .distinct()[:200],
        }
    )
    ps_names = sorted(
        set(
            InOrder.objects.filter(completion_date__gte=start - timedelta(days=30))
            .exclude(solution__payment_system__name__isnull=True)
            .values_list("solution__payment_system__name", flat=True)
            .distinct()[:100]
        )
    )

    return {
        "timezone": "Europe/Moscow",
        "preset": kind,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "filters": {
            "merchant": merchant,
            "psp": psp,
            "ps": ps,
            "direction": direction,
        },
        "kpi": {
            "turnover_usd": money_str(turnover),
            "net": money_str(net),
            "margin_pct": _pct(net, turnover) if turnover > 0 else "0.00",
            "orders_in": in_agg["count"],
            "orders_out": out_agg["count"],
            "conv_create_pct": _pct(success, created),
            "conv_issued_pct": _pct(success, issued),
            "fx": money_str(payin_fx),
        },
        "daily": daily,
        "conversion": {
            "created": created,
            "declined": declined,
            "issued": issued,
            "success": success,
            "create_to_success_pct": _pct(success, created),
            "issued_to_success_pct": _pct(success, issued),
        },
        "pnl": {
            "payin_mdr": money_str(payin_mdr),
            "payin_fx": money_str(payin_fx),
            "payout_mdr": money_str(payout_mdr),
            "trader_fee": money_str(payin_trader + payout_trader),
            "agent_fee": money_str(agent),
            "expenses": money_str(expense_total),
            "expense_count": expense_count,
            "expenses_scoped": include_expenses,
            "net": money_str(net),
        },
        "by_merchant": by_merchant,
        "by_psp": by_psp,
        "filter_options": {
            "merchants": list(merchant_names),
            "psps": [n for n in psp_names if n],
            "payment_systems": list(ps_names),
        },
    }
