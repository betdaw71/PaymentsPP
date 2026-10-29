"""
Django shell: статистика за день по Completed InOrder / OutOrder + конверсия PayIn.

  docker compose exec app python manage.py daily_stats --yesterday
  docker compose exec app python manage.py daily_stats 2026-07-24
  docker compose exec app python manage.py daily_stats --yesterday --merchant pandapay

Shell:
  exec(open("basics/shell_daily_stats.py").read())
  run(yesterday=True)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from payments.models import PayIn
from trade.models import InOrder, OutOrder

PSP_TRADER_USERNAMES = frozenset({"protocol1", "expayone1", "fairpay1", "playments1"})


def _d(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def _resolve_day(target: date | None, *, yesterday: bool) -> date:
    if yesterday:
        return timezone.localdate() - timedelta(days=1)
    if target is not None:
        return target
    return timezone.localdate()


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = start + timedelta(days=1)
    return start, end


def _agg_in_qs(qs):
    return qs.aggregate(
        count=Count("id"),
        amount=Sum("amount"),
        amount_usd=Sum("usd_amount"),
        merchant_fee=Sum("merchant_fee"),
        trader_fee=Sum("trader_fee"),
    )


def _agg_out_qs(qs):
    return qs.aggregate(
        count=Count("id"),
        amount=Sum("amount"),
        amount_usd=Sum("usd_amount"),
        merchant_fee=Sum("merchant_fee"),
        trader_fee=Sum("trader_fee"),
    )


def _print_agg_row(label: str, agg: dict, currency_sym: str = ""):
    cnt = agg.get("count") or 0
    amt = _d(agg.get("amount"))
    usd = _d(agg.get("amount_usd"))
    mf = _d(agg.get("merchant_fee"))
    tf = _d(agg.get("trader_fee"))
    fiat = f" {amt:,.2f} {currency_sym}".strip() if currency_sym else f" {amt:,.2f}"
    print(
        f"  {label}: count={cnt} | fiat={fiat} | USD={usd:,.2f} | "
        f"merchant_fee={mf:,.2f} | trader_fee={tf:,.2f}"
    )


def _group_in(qs, *fields):
    return list(
        qs.values(*fields).annotate(
            count=Count("id"),
            amount=Sum("amount"),
            amount_usd=Sum("usd_amount"),
            merchant_fee=Sum("merchant_fee"),
            trader_fee=Sum("trader_fee"),
        )
    )


def _group_out(qs, *fields):
    return list(
        qs.values(*fields).annotate(
            count=Count("id"),
            amount=Sum("amount"),
            amount_usd=Sum("usd_amount"),
            merchant_fee=Sum("merchant_fee"),
            trader_fee=Sum("trader_fee"),
        )
    )


def _print_conversion(day: date, merchant: str | None):
    start, end = _day_bounds(day)
    payins = PayIn.objects.filter(created_at__gte=start, created_at__lt=end)
    if merchant:
        payins = payins.filter(merchant__user__username=merchant)

    total = payins.count()
    declined = payins.filter(status__name="Declined").count()
    issued = total - declined
    success = payins.filter(status__name="Success").count()

    print("\n=== КОНВЕРСИЯ PAY-IN (когорта по created_at) ===")
    print(f"  Создано: {total}")
    print(f"  Declined (без рек): {declined}")
    print(f"  Выдан рек (не Declined): {issued}")
    print(f"  Success: {success}")
    if issued:
        print(f"  Конверсия рек → Success: {100 * success / issued:.1f}%")
    if total:
        print(f"  Конверсия create → Success: {100 * success / total:.1f}%")

    in_orders = InOrder.objects.filter(
        creation_date__gte=start,
        creation_date__lt=end,
        payment_details__isnull=False,
    ).exclude(payment_details__group__trader__user__username__in=PSP_TRADER_USERNAMES)
    if merchant:
        in_orders = in_orders.filter(solution__merchant__user__username=merchant)

    assigned = in_orders.count()
    completed = in_orders.filter(status__name="Completed").count()
    print("\n=== КОНВЕРСИЯ IN-ORDER (трейдеры, без PSP) ===")
    print(f"  Назначено рек: {assigned}")
    print(f"  Completed: {completed}")
    if assigned:
        print(f"  Конверсия рек → Completed: {100 * completed / assigned:.1f}%")


def run(target: date | None = None, *, yesterday: bool = False, merchant: str | None = None):
    day = _resolve_day(target, yesterday=yesterday)
    start, end = _day_bounds(day)

    print("=" * 72)
    print(f"DAILY STATS  {day.isoformat()}  ({timezone.get_current_timezone()})")
    if merchant:
        print(f"  merchant filter: {merchant}")
    print("=" * 72)

    in_qs = InOrder.objects.filter(
        status__name="Completed",
        completion_date__gte=start,
        completion_date__lt=end,
    ).select_related("solution__payment_system__currency", "solution__merchant__user")
    out_qs = OutOrder.objects.filter(
        status__name="Completed",
        completion_date__gte=start,
        completion_date__lt=end,
    ).select_related("solution__payment_system__currency", "solution__merchant__user")

    if merchant:
        in_qs = in_qs.filter(solution__merchant__user__username=merchant)
        out_qs = out_qs.filter(solution__merchant__user__username=merchant)

    print("\n=== ИТОГО (Completed по completion_date) ===")
    _print_agg_row("IN ", _agg_in_qs(in_qs))
    _print_agg_row("OUT", _agg_out_qs(out_qs))

    print("\n=== ПО PAYMENT SYSTEM (IN) ===")
    for row in sorted(_group_in(in_qs, "solution__payment_system__name"), key=lambda r: -_d(r["amount_usd"])):
        ps = row["solution__payment_system__name"]
        _print_agg_row(ps, row)

    print("\n=== ПО ВАЛЮТЕ (IN) ===")
    for row in sorted(_group_in(in_qs, "solution__payment_system__currency__symbol"), key=lambda r: -_d(r["amount"])):
        sym = row["solution__payment_system__currency__symbol"] or "?"
        _print_agg_row(sym, row, currency_sym=sym)

    print("\n=== МЕРЧАНТЫ (IN, top 20 по USD) ===")
    for row in sorted(
        _group_in(in_qs, "solution__merchant__user__username"),
        key=lambda r: -_d(r["amount_usd"]),
    )[:20]:
        name = row["solution__merchant__user__username"]
        _print_agg_row(name, row)

    print("\n=== ТРЕЙДЕРЫ (IN, top 20 по USD) ===")
    for row in sorted(
        _group_in(in_qs, "payment_details__group__trader__user__username"),
        key=lambda r: -_d(r["amount_usd"]),
    )[:20]:
        name = row["payment_details__group__trader__user__username"] or "(no trader)"
        _print_agg_row(name, row)

    print("\n=== КОМАНДЫ (IN) ===")
    for row in sorted(
        _group_in(in_qs, "payment_details__group__trader__team__name"),
        key=lambda r: -_d(r["amount_usd"]),
    ):
        name = row["payment_details__group__trader__team__name"] or "(no team)"
        _print_agg_row(name, row)

    _print_conversion(day, merchant)
    print("\n" + "=" * 72)


if __name__ == "__main__":
    run()
else:
    print("Run: run() | run(yesterday=True) | run(date(2026, 7, 24))")
