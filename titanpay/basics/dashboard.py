from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from basics.models import Currency, PaymentSystem, Trader
from basics.serializers import PaymentSystemExchangeRateSerializer
from merchant.models import Merchant
from trade.models import InOrder, OutOrder, WithdrawalRequest


def _to_float(value):
    if value is None:
        return 0.0
    return float(value)


def _parse_period(period):
    today = timezone.now().date()
    if period == "day":
        return today, period
    if period == "30d":
        return today - timedelta(days=30), period
    return today - timedelta(days=7), "7d"


def _apply_order_filters(qs, payment_system_id=None, currency_symbol=None):
    if payment_system_id:
        qs = qs.filter(solution__payment_system_id=payment_system_id)
    if currency_symbol:
        qs = qs.filter(solution__payment_system__currency__symbol=currency_symbol)
    return qs


def _order_stats(qs, completed_only=False):
    if completed_only:
        qs = qs.filter(status__name="Completed")
    agg = qs.aggregate(
        count=Count("id"),
        usd=Sum("usd_amount"),
        margin=Sum(F("merchant_fee") - F("trader_fee")),
    )
    total = qs.count() if not completed_only else agg["count"]
    return {
        "count": agg["count"] or 0,
        "usd": _to_float(agg["usd"]),
        "margin": _to_float(agg["margin"]),
        "total_count": total,
    }


def _funnel(qs):
    rows = (
        qs.values("status__name")
        .annotate(count=Count("id"), usd=Sum("usd_amount"))
        .order_by("-count")
    )
    return [
        {
            "status": row["status__name"] or "Unknown",
            "count": row["count"],
            "usd": _to_float(row["usd"]),
        }
        for row in rows
    ]


def _daily_chart(qs_in, qs_out, start_date):
    in_rows = (
        qs_in.filter(status__name="Completed", creation_date__date__gte=start_date)
        .annotate(day=TruncDate("creation_date"))
        .values("day")
        .annotate(usd=Sum("usd_amount"), count=Count("id"), margin=Sum(F("merchant_fee") - F("trader_fee")))
        .order_by("day")
    )
    out_rows = (
        qs_out.filter(status__name="Completed", creation_date__date__gte=start_date)
        .annotate(day=TruncDate("creation_date"))
        .values("day")
        .annotate(usd=Sum("usd_amount"), count=Count("id"), margin=Sum(F("merchant_fee") - F("trader_fee")))
        .order_by("day")
    )

    in_map = {row["day"]: row for row in in_rows}
    out_map = {row["day"]: row for row in out_rows}
    days = sorted(set(in_map.keys()) | set(out_map.keys()))

    result = []
    for day in days:
        in_row = in_map.get(day, {})
        out_row = out_map.get(day, {})
        result.append(
            {
                "date": day.isoformat(),
                "in_usd": _to_float(in_row.get("usd")),
                "out_usd": _to_float(out_row.get("usd")),
                "in_count": in_row.get("count") or 0,
                "out_count": out_row.get("count") or 0,
                "margin": _to_float(in_row.get("margin")) + _to_float(out_row.get("margin")),
            }
        )
    return result


def _by_payment_system(qs_in, qs_out):
    in_rows = (
        qs_in.values(
            "solution__payment_system__id",
            "solution__payment_system__name",
            "solution__payment_system__currency__symbol",
        )
        .annotate(
            in_count=Count("id"),
            in_usd=Sum("usd_amount"),
            in_completed=Count("id", filter=Q(status__name="Completed")),
            in_completed_usd=Sum("usd_amount", filter=Q(status__name="Completed")),
            in_margin=Sum(F("merchant_fee") - F("trader_fee"), filter=Q(status__name="Completed")),
        )
    )
    out_rows = (
        qs_out.values(
            "solution__payment_system__id",
            "solution__payment_system__name",
            "solution__payment_system__currency__symbol",
        )
        .annotate(
            out_count=Count("id"),
            out_usd=Sum("usd_amount"),
            out_completed=Count("id", filter=Q(status__name="Completed")),
            out_completed_usd=Sum("usd_amount", filter=Q(status__name="Completed")),
            out_margin=Sum(F("merchant_fee") - F("trader_fee"), filter=Q(status__name="Completed")),
        )
    )

    merged = {}
    for row in in_rows:
        ps_id = str(row["solution__payment_system__id"])
        merged[ps_id] = {
            "id": ps_id,
            "name": row["solution__payment_system__name"],
            "currency": row["solution__payment_system__currency__symbol"],
            "in_count": row["in_count"],
            "in_usd": _to_float(row["in_usd"]),
            "in_completed": row["in_completed"],
            "in_completed_usd": _to_float(row["in_completed_usd"]),
            "in_margin": _to_float(row["in_margin"]),
            "out_count": 0,
            "out_usd": 0.0,
            "out_completed": 0,
            "out_completed_usd": 0.0,
            "out_margin": 0.0,
        }

    for row in out_rows:
        ps_id = str(row["solution__payment_system__id"])
        if ps_id not in merged:
            merged[ps_id] = {
                "id": ps_id,
                "name": row["solution__payment_system__name"],
                "currency": row["solution__payment_system__currency__symbol"],
                "in_count": 0,
                "in_usd": 0.0,
                "in_completed": 0,
                "in_completed_usd": 0.0,
                "in_margin": 0.0,
            }
        merged[ps_id].update(
            {
                "out_count": row["out_count"],
                "out_usd": _to_float(row["out_usd"]),
                "out_completed": row["out_completed"],
                "out_completed_usd": _to_float(row["out_completed_usd"]),
                "out_margin": _to_float(row["out_margin"]),
            }
        )

    rows = list(merged.values())
    for row in rows:
        row["margin"] = row["in_margin"] + row["out_margin"]
        in_total = row["in_count"] or 0
        out_total = row["out_count"] or 0
        row["in_conversion"] = round(100 * row["in_completed"] / in_total, 2) if in_total else 0
        row["out_conversion"] = round(100 * row["out_completed"] / out_total, 2) if out_total else 0
    rows.sort(key=lambda item: item["in_completed_usd"] + item["out_completed_usd"], reverse=True)
    return rows


def _by_currency(qs_in, qs_out):
    in_rows = (
        qs_in.values("solution__payment_system__currency__symbol")
        .annotate(
            in_count=Count("id"),
            in_completed=Count("id", filter=Q(status__name="Completed")),
            in_completed_usd=Sum("usd_amount", filter=Q(status__name="Completed")),
            in_margin=Sum(F("merchant_fee") - F("trader_fee"), filter=Q(status__name="Completed")),
        )
    )
    out_rows = (
        qs_out.values("solution__payment_system__currency__symbol")
        .annotate(
            out_count=Count("id"),
            out_completed=Count("id", filter=Q(status__name="Completed")),
            out_completed_usd=Sum("usd_amount", filter=Q(status__name="Completed")),
            out_margin=Sum(F("merchant_fee") - F("trader_fee"), filter=Q(status__name="Completed")),
        )
    )

    merged = {}
    for row in in_rows:
        symbol = row["solution__payment_system__currency__symbol"] or "?"
        merged[symbol] = {
            "currency": symbol,
            "in_count": row["in_count"],
            "in_completed": row["in_completed"],
            "in_completed_usd": _to_float(row["in_completed_usd"]),
            "in_margin": _to_float(row["in_margin"]),
            "out_count": 0,
            "out_completed": 0,
            "out_completed_usd": 0.0,
            "out_margin": 0.0,
        }

    for row in out_rows:
        symbol = row["solution__payment_system__currency__symbol"] or "?"
        if symbol not in merged:
            merged[symbol] = {
                "currency": symbol,
                "in_count": 0,
                "in_completed": 0,
                "in_completed_usd": 0.0,
                "in_margin": 0.0,
            }
        merged[symbol].update(
            {
                "out_count": row["out_count"],
                "out_completed": row["out_completed"],
                "out_completed_usd": _to_float(row["out_completed_usd"]),
                "out_margin": _to_float(row["out_margin"]),
            }
        )

    rows = list(merged.values())
    for row in rows:
        row["margin"] = row["in_margin"] + row["out_margin"]
        row["total_completed_usd"] = row["in_completed_usd"] + row["out_completed_usd"]
        in_total = row["in_count"] or 0
        out_total = row["out_count"] or 0
        row["in_conversion"] = round(100 * row["in_completed"] / in_total, 2) if in_total else 0
        row["out_conversion"] = round(100 * row["out_completed"] / out_total, 2) if out_total else 0
    rows.sort(key=lambda item: item["total_completed_usd"], reverse=True)
    return rows


def _balances():
    traders = Trader.objects.aggregate(
        available=Sum("balance_usdt__amount"),
        frozen=Sum("frozen_balance_usdt__amount"),
    )
    merchants = Merchant.objects.aggregate(
        available=Sum("balance__amount"),
        frozen=Sum("frozen_balance__amount"),
    )
    return {
        "traders_available": _to_float(traders["available"]),
        "traders_frozen": _to_float(traders["frozen"]),
        "merchants_available": _to_float(merchants["available"]),
        "merchants_frozen": _to_float(merchants["frozen"]),
    }


def _queues(payment_system_id=None, currency_symbol=None):
    qs_in = _apply_order_filters(InOrder.objects.all(), payment_system_id, currency_symbol)
    qs_out = _apply_order_filters(OutOrder.objects.all(), payment_system_id, currency_symbol)
    withdrawals = WithdrawalRequest.objects.filter(status=0).aggregate(
        count=Count("id"),
        amount=Sum("amount"),
    )
    return {
        "pending_withdrawals": withdrawals["count"] or 0,
        "pending_withdrawals_usd": _to_float(withdrawals["amount"]),
        "manual_check_out": qs_out.filter(status__name="Manual check").count(),
        "arbitrage_in": qs_in.filter(status__name="Arbitrage").count(),
        "arbitrage_out": qs_out.filter(status__name="Arbitrage").count(),
        "cannot_process_in": qs_in.filter(status__name="Cannot process").count(),
        "cannot_process_out": qs_out.filter(status__name="Cannot process").count(),
    }


def build_dashboard_data(request):
    period = request.GET.get("period", "7d")
    payment_system_id = request.GET.get("payment_system") or None
    currency_symbol = request.GET.get("currency") or None

    start_date, period = _parse_period(period)
    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))

    qs_in = _apply_order_filters(
        InOrder.objects.filter(creation_date__gte=start_dt),
        payment_system_id,
        currency_symbol,
    )
    qs_out = _apply_order_filters(
        OutOrder.objects.filter(creation_date__gte=start_dt),
        payment_system_id,
        currency_symbol,
    )

    in_all = _order_stats(qs_in)
    in_completed = _order_stats(qs_in, completed_only=True)
    out_all = _order_stats(qs_out)
    out_completed = _order_stats(qs_out, completed_only=True)

    in_conversion = round(100 * in_completed["count"] / in_all["count"], 2) if in_all["count"] else 0
    out_conversion = round(100 * out_completed["count"] / out_all["count"], 2) if out_all["count"] else 0

    payment_systems = PaymentSystem.objects.select_related("currency").order_by("name")
    currencies = Currency.objects.all().order_by("symbol")

    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "filters": {
            "payment_systems": [
                {
                    "id": str(ps.id),
                    "name": ps.name,
                    "currency": ps.currency.symbol if ps.currency else None,
                }
                for ps in payment_systems
            ],
            "currencies": [{"symbol": c.symbol, "name": c.name} for c in currencies],
        },
        "applied_filters": {
            "payment_system": payment_system_id,
            "currency": currency_symbol,
        },
        "kpi": {
            "in_created": in_all["count"],
            "out_created": out_all["count"],
            "in_completed": in_completed["count"],
            "out_completed": out_completed["count"],
            "in_turnover_usd": in_completed["usd"],
            "out_turnover_usd": out_completed["usd"],
            "margin_usd": in_completed["margin"] + out_completed["margin"],
            "in_conversion": in_conversion,
            "out_conversion": out_conversion,
            **_balances(),
            **_queues(payment_system_id, currency_symbol),
        },
        "funnel_in": _funnel(qs_in),
        "funnel_out": _funnel(qs_out),
        "daily_chart": _daily_chart(qs_in, qs_out, start_date),
        "by_payment_system": _by_payment_system(qs_in, qs_out),
        "by_currency": _by_currency(qs_in, qs_out),
        "exchange_rates": PaymentSystemExchangeRateSerializer(payment_systems, many=True).data,
    }
