"""
Django shell: статистика за день по Completed InOrder / OutOrder + конверсия PayIn.

merchant_fee для Melbet (KZT/KGS) конвертируется в USDT: fee * usd_amount / amount.
День считается по Europe/Moscow (как касса).

  docker compose exec app python manage.py daily_stats --yesterday
  docker compose exec app python manage.py daily_stats 2026-07-24
  docker compose exec app python manage.py daily_stats --yesterday --merchant pandapay

Shell:
  exec(open("basics/shell_daily_stats.py").read())
  run(yesterday=True)
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from payments.models import PayIn
from trade.models import InOrder, OutOrder

PSP_TRADER_USERNAMES = frozenset({"protocol1", "expayone1", "fairpay1", "playments1"})
ZERO = Decimal("0.00")
DEC = DecimalField(max_digits=32, decimal_places=2)
MSK = ZoneInfo("Europe/Moscow")


def _d(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def _mdr_usd_expr():
    try:
        from basics.cash_register import melbet_fiat_merchant_fee_usd_expr

        return melbet_fiat_merchant_fee_usd_expr()
    except ImportError:
        from merchant.kzt_settlement import (
            melbet_kgs_ps_names,
            melbet_kzt_ps_names,
            melbet_kzt_usernames,
        )

        melbet_names = sorted(melbet_kzt_usernames()) or ["melbet", "melbet_test"]
        fiat_ps = sorted(
            {
                *(n.upper() for n in melbet_kzt_ps_names()),
                *(n.upper() for n in melbet_kgs_ps_names()),
            }
        )
        fiat_fee_usd = ExpressionWrapper(
            F("merchant_fee") * F("usd_amount") / F("amount"),
            output_field=DEC,
        )
        return Case(
            When(
                solution__merchant__user__username__in=melbet_names,
                solution__payment_system__name__in=fiat_ps,
                amount__gt=0,
                usd_amount__gt=0,
                then=fiat_fee_usd,
            ),
            When(
                solution__merchant__user__username__in=melbet_names,
                solution__payment_system__currency__symbol__in=["KZT", "KGS"],
                amount__gt=0,
                usd_amount__gt=0,
                then=fiat_fee_usd,
            ),
            When(
                solution__merchant__user__username__in=melbet_names,
                merchant_fee__gt=F("usd_amount"),
                amount__gt=0,
                usd_amount__gt=0,
                then=fiat_fee_usd,
            ),
            default=F("merchant_fee"),
            output_field=DEC,
        )


def _resolve_day(target: date | None, *, yesterday: bool) -> date:
    today_msk = datetime.now(MSK).date()
    if yesterday:
        return today_msk - timedelta(days=1)
    if target is not None:
        return target
    return today_msk


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=MSK)
    end = start + timedelta(days=1)
    return start, end


def _agg_in_qs(qs):
    mdr = _mdr_usd_expr()
    return qs.aggregate(
        count=Count("id"),
        amount=Sum("amount"),
        amount_usd=Sum("usd_amount"),
        merchant_fee_raw=Coalesce(Sum("merchant_fee"), Value(ZERO, output_field=DEC)),
        merchant_fee=Coalesce(Sum(mdr), Value(ZERO, output_field=DEC)),
        trader_fee=Sum("trader_fee"),
        agent_fee=Coalesce(Sum("agent_fee"), Value(ZERO, output_field=DEC)),
        fx_spread=Coalesce(
            Sum(
                ExpressionWrapper(
                    Case(
                        When(psp_usd_amount__gt=0, then=F("psp_usd_amount")),
                        default=F("usd_amount"),
                        output_field=DEC,
                    )
                    - F("usd_amount"),
                    output_field=DEC,
                )
            ),
            Value(ZERO, output_field=DEC),
        ),
    )


def _agg_out_qs(qs):
    mdr = _mdr_usd_expr()
    return qs.aggregate(
        count=Count("id"),
        amount=Sum("amount"),
        amount_usd=Sum("usd_amount"),
        merchant_fee_raw=Coalesce(Sum("merchant_fee"), Value(ZERO, output_field=DEC)),
        merchant_fee=Coalesce(Sum(mdr), Value(ZERO, output_field=DEC)),
        trader_fee=Sum("trader_fee"),
    )


def _print_agg_row(label: str, agg: dict, currency_sym: str = "", *, show_raw: bool = False):
    cnt = agg.get("count") or 0
    amt = _d(agg.get("amount"))
    usd = _d(agg.get("amount_usd"))
    mf = _d(agg.get("merchant_fee"))
    tf = _d(agg.get("trader_fee"))
    fiat = f" {amt:,.2f} {currency_sym}".strip() if currency_sym else f" {amt:,.2f}"
    extra = ""
    if show_raw and "merchant_fee_raw" in agg:
        raw = _d(agg.get("merchant_fee_raw"))
        if raw != mf:
            extra = f" | merchant_fee_raw={raw:,.2f}"
    print(
        f"  {label}: count={cnt} | fiat={fiat} | USD={usd:,.2f} | "
        f"merchant_fee_usd={mf:,.2f} | trader_fee={tf:,.2f}{extra}"
    )


def _group_in(qs, *fields):
    mdr = _mdr_usd_expr()
    return list(
        qs.values(*fields).annotate(
            count=Count("id"),
            amount=Sum("amount"),
            amount_usd=Sum("usd_amount"),
            merchant_fee_raw=Coalesce(Sum("merchant_fee"), Value(ZERO, output_field=DEC)),
            merchant_fee=Coalesce(Sum(mdr), Value(ZERO, output_field=DEC)),
            trader_fee=Sum("trader_fee"),
        )
    )


def _group_out(qs, *fields):
    mdr = _mdr_usd_expr()
    return list(
        qs.values(*fields).annotate(
            count=Count("id"),
            amount=Sum("amount"),
            amount_usd=Sum("usd_amount"),
            merchant_fee=Coalesce(Sum(mdr), Value(ZERO, output_field=DEC)),
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


def _print_day_pnl(in_agg: dict, out_agg: dict, day: date):
    start, end = _day_bounds(day)
    payin_mdr = _d(in_agg.get("merchant_fee"))
    payin_fx = _d(in_agg.get("fx_spread"))
    payout_mdr = _d(out_agg.get("merchant_fee"))
    trader = _d(in_agg.get("trader_fee")) + _d(out_agg.get("trader_fee"))
    agent = _d(in_agg.get("agent_fee"))
    expenses = ZERO
    expense_n = 0
    try:
        from basics.models import PlatformExpense

        exp = PlatformExpense.objects.filter(created_at__gte=start, created_at__lt=end).aggregate(
            total=Coalesce(Sum("amount"), Value(ZERO, output_field=DEC)),
            count=Count("id"),
        )
        expenses = _d(exp["total"])
        expense_n = exp["count"] or 0
    except Exception:
        pass
    net = payin_mdr + payin_fx + payout_mdr - trader - agent - expenses
    print("\n=== PnL ДНЯ (как касса, Europe/Moscow) ===")
    print(f"  + MDR in USD:  {payin_mdr:,.2f}  (raw fee sum={_d(in_agg.get('merchant_fee_raw')):,.2f})")
    print(f"  + FX:          {payin_fx:,.2f}")
    print(f"  + MDR out USD: {payout_mdr:,.2f}")
    print(f"  − PSP fee:     {trader:,.2f}")
    print(f"  − агент:       {agent:,.2f}")
    print(f"  − расходы:     {expenses:,.2f}  (n={expense_n})")
    print(f"  NET:           {net:,.2f} USDT")


def run(target: date | None = None, *, yesterday: bool = False, merchant: str | None = None):
    day = _resolve_day(target, yesterday=yesterday)
    start, end = _day_bounds(day)

    print("=" * 72)
    print(f"DAILY STATS  {day.isoformat()}  (Europe/Moscow)")
    print(f"  window: {start.isoformat()} → {end.isoformat()}")
    if merchant:
        print(f"  merchant filter: {merchant}")
    print("  merchant_fee_usd: Melbet KZT/KGS fee → USDT (fee*usd/amount)")
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

    in_agg = _agg_in_qs(in_qs)
    out_agg = _agg_out_qs(out_qs)

    print("\n=== ИТОГО (Completed по completion_date) ===")
    _print_agg_row("IN ", in_agg, show_raw=True)
    _print_agg_row("OUT", out_agg, show_raw=True)

    print("\n=== ПО PAYMENT SYSTEM (IN) ===")
    for row in sorted(_group_in(in_qs, "solution__payment_system__name"), key=lambda r: -_d(r["amount_usd"])):
        ps = row["solution__payment_system__name"]
        _print_agg_row(ps, row, show_raw=True)

    print("\n=== ПО ВАЛЮТЕ (IN) ===")
    for row in sorted(_group_in(in_qs, "solution__payment_system__currency__symbol"), key=lambda r: -_d(r["amount"])):
        sym = row["solution__payment_system__currency__symbol"] or "?"
        _print_agg_row(sym, row, currency_sym=sym, show_raw=True)

    print("\n=== МЕРЧАНТЫ (IN, top 20 по USD) ===")
    for row in sorted(
        _group_in(in_qs, "solution__merchant__user__username"),
        key=lambda r: -_d(r["amount_usd"]),
    )[:20]:
        name = row["solution__merchant__user__username"]
        _print_agg_row(name, row, show_raw=True)

    print("\n=== ТРЕЙДЕРЫ (IN, top 20 по USD) ===")
    for row in sorted(
        _group_in(in_qs, "payment_details__group__trader__user__username"),
        key=lambda r: -_d(r["amount_usd"]),
    )[:20]:
        name = row["payment_details__group__trader__user__username"] or "(no trader)"
        _print_agg_row(name, row, show_raw=True)

    print("\n=== КОМАНДЫ (IN) ===")
    for row in sorted(
        _group_in(in_qs, "payment_details__group__trader__team__name"),
        key=lambda r: -_d(r["amount_usd"]),
    ):
        name = row["payment_details__group__trader__team__name"] or "(no team)"
        _print_agg_row(name, row, show_raw=True)

    _print_conversion(day, merchant)
    if not merchant:
        _print_day_pnl(in_agg, out_agg, day)
    print("\n" + "=" * 72)


if __name__ == "__main__":
    run()
else:
    print("Run: run() | run(yesterday=True) | run(date(2026, 7, 24))")
