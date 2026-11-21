"""Курсовой gap: ожидаемый FX по тетради vs фактически записанный на ордерах.

До dual FX (миграции 0007 / деплой ~2026-10-27) на InOrder не писались
merchant_rate / psp_rate / psp_usd_amount → в кассе FX≈0, хотя условия xe+N
уже были. Этот скрипт считает, сколько курсового дохода «потеряли» за период.

Формула (как dual_fx.quote_dual_fx):
  merchant_rate = amount / usd_amount  (или order.merchant_rate)
  psp_rate      = merchant_rate * psp_markup / merchant_markup
  expected_psp  = amount / psp_rate
  expected_fx   = expected_psp − merchant_usd
  actual_fx     = effective_psp_usd − merchant_usd
  gap           = expected_fx − actual_fx

Октябрь 2026, Patriot + VisionX:
  docker compose exec -T -e YEAR=2026 -e MONTH=10 \\
    -e TRADERS=patriot1,visionx1 app python manage.py shell \\
    < titanpay/basics/shell_fx_margin_gap.py

Из контейнера (/app):
  YEAR=2026 MONTH=10 TRADERS=patriot1,visionx1 \\
    python manage.py shell < basics/shell_fx_margin_gap.py

Опционально:
  DUAL_FX_SINCE=2026-10-27   — граница «до/после фикса» (MSK)
  MERCHANT=melbet            — фильтр мерчанта
  ALL_PSP=1                  — все трейдеры из PSP_XE_MARKUP_BY_TRADER
"""
from __future__ import annotations

import json
import os
from calendar import monthrange
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.conf import settings

from basics.utils import DEFAULT_XE_KZT_MARKUP, xe_kzt_markup_for_ps
from trade.models import InOrder

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
Q3 = Decimal("0.001")
ZERO = Decimal("0.00")

YEAR = int(os.environ.get("YEAR") or "2026")
MONTH = int(os.environ.get("MONTH") or "10")
MERCHANT = (os.environ.get("MERCHANT") or "").strip()
ALL_PSP = (os.environ.get("ALL_PSP") or "").strip().lower() in {"1", "true", "yes"}
DUAL_FX_SINCE_RAW = (os.environ.get("DUAL_FX_SINCE") or "2026-10-27").strip()


def money(raw) -> Decimal:
    return Decimal(str(raw or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def money_str(raw) -> str:
    return f"{money(raw):,.2f}"


def pct(part, whole) -> str:
    whole = money(whole)
    if whole <= 0:
        return "n/a"
    return f"{100 * money(part) / whole:.2f}%"


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    _ = monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=MSK)
    if month == 12:
        end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=MSK)
    else:
        end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=MSK)
    return start, end


def parse_dual_fx_since(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        day = datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=MSK)
    except ValueError:
        return None
    return day


def psp_markup_map() -> dict[str, Decimal]:
    raw = getattr(settings, "PSP_XE_MARKUP_BY_TRADER", None) or ""
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(str(raw)) if str(raw).strip() else {}
        except Exception:
            data = {}
    out: dict[str, Decimal] = {}
    for key, val in (data or {}).items():
        try:
            out[str(key).strip().lower()] = Decimal(str(val))
        except Exception:
            continue
    return out


def trader_list(markups: dict[str, Decimal]) -> list[str]:
    raw = (os.environ.get("TRADERS") or "").strip()
    if ALL_PSP:
        return sorted(markups.keys())
    if raw:
        return [x.strip().lower() for x in raw.split(",") if x.strip()]
    return ["patriot1", "visionx1"]


def empty_bucket():
    return {
        "n": 0,
        "usd": ZERO,
        "actual_psp": ZERO,
        "expected_psp": ZERO,
        "actual_fx": ZERO,
        "expected_fx": ZERO,
        "gap": ZERO,
        "with_dual": 0,
        "without_dual": 0,
        "gap_without": ZERO,
        "gap_with": ZERO,
    }


def add_row(bucket, *, usd, actual_psp, expected_psp, actual_fx, expected_fx, gap, has_dual: bool):
    bucket["n"] += 1
    bucket["usd"] += usd
    bucket["actual_psp"] += actual_psp
    bucket["expected_psp"] += expected_psp
    bucket["actual_fx"] += actual_fx
    bucket["expected_fx"] += expected_fx
    bucket["gap"] += gap
    if has_dual:
        bucket["with_dual"] += 1
        bucket["gap_with"] += gap
    else:
        bucket["without_dual"] += 1
        bucket["gap_without"] += gap


def order_has_dual_fx(order) -> bool:
    psp = money(order.psp_usd_amount)
    usd = money(order.usd_amount)
    if psp > 0 and psp != usd:
        return True
    mr = money(getattr(order, "merchant_rate", 0) or 0)
    pr = money(getattr(order, "psp_rate", 0) or 0)
    return mr > 0 and pr > 0 and mr != pr


def expected_psp_usd(*, amount: Decimal, merchant_usd: Decimal, merchant_rate, merchant_markup: Decimal, psp_markup: Decimal) -> Decimal:
    """Ожидаемый psp_usd по сетке markups (без live XE — от курса мерчанта на ордере)."""
    if amount <= 0 or merchant_usd <= 0 or merchant_markup <= 0 or psp_markup <= 0:
        return merchant_usd
    if psp_markup == merchant_markup:
        return merchant_usd
    rate = Decimal(str(merchant_rate or 0))
    if rate <= 0:
        rate = (amount / merchant_usd).quantize(Q3, rounding=ROUND_HALF_UP)
    psp_rate = (rate * psp_markup / merchant_markup).quantize(Q3, rounding=ROUND_HALF_UP)
    if psp_rate <= 0:
        return merchant_usd
    return money(amount / psp_rate)


def print_bucket(title: str, b: dict) -> None:
    print(f"\n--- {title} ---")
    print(f"  n={b['n']}  (dual_fx записан: {b['with_dual']} / без dual: {b['without_dual']})")
    print(f"  merchant USD:     {money_str(b['usd'])}")
    print(f"  actual psp USD:   {money_str(b['actual_psp'])}")
    print(f"  expected psp USD: {money_str(b['expected_psp'])}")
    print(f"  actual FX:        {money_str(b['actual_fx'])}  ({pct(b['actual_fx'], b['usd'])})")
    print(f"  expected FX:      {money_str(b['expected_fx'])}  ({pct(b['expected_fx'], b['usd'])})")
    print(f"  GAP (недобор):    {money_str(b['gap'])}  ({pct(b['gap'], b['usd'])})")
    if b["without_dual"]:
        print(f"    └ gap на сделках БЕЗ dual: {money_str(b['gap_without'])}")
    if b["with_dual"]:
        print(f"    └ gap на сделках С dual:   {money_str(b['gap_with'])}")


def run() -> None:
    start, end = month_bounds(YEAR, MONTH)
    dual_since = parse_dual_fx_since(DUAL_FX_SINCE_RAW)
    markups = psp_markup_map()
    traders = trader_list(markups)

    print("=" * 72)
    print(f"FX MARGIN GAP  {YEAR}-{MONTH:02d}  (Europe/Moscow)")
    print(f"  window: {start.isoformat()} → {end.isoformat()}")
    print(f"  traders: {', '.join(traders)}")
    if MERCHANT:
        print(f"  merchant: {MERCHANT}")
    print(f"  dual_fx since (MSK day): {dual_since.date().isoformat() if dual_since else 'n/a'}")
    print("  note: dual FX в коде с ~2026-10-27; до этого psp_usd/rates=0 → FX в кассе=0")
    print("=" * 72)

    print("\nconfigured PSP_XE_MARKUP_BY_TRADER:")
    for name in traders:
        m = markups.get(name)
        if m is None:
            print(f"  {name}: NOT IN MAP (fallback=merchant → expected FX=0)")
        else:
            spread = (DEFAULT_XE_KZT_MARKUP / m - 1) if m else ZERO
            print(
                f"  {name}: xe*{m}  vs merchant default xe*{DEFAULT_XE_KZT_MARKUP}"
                f"  → theor FX≈{100 * spread:.2f}% of merchant USD"
            )

    qs = (
        InOrder.objects.filter(
            status__name="Completed",
            completion_date__gte=start,
            completion_date__lt=end,
            payment_details__group__trader__user__username__in=traders,
        )
        .select_related(
            "solution__payment_system__currency",
            "solution__merchant__user",
            "payment_details__group__trader__user",
        )
        .order_by("completion_date", "id")
    )
    if MERCHANT:
        qs = qs.filter(solution__merchant__user__username=MERCHANT)

    by_trader: dict[str, dict] = defaultdict(empty_bucket)
    by_period: dict[str, dict] = {
        "before_dual_fx": empty_bucket(),
        "on_after_dual_fx": empty_bucket(),
        "TOTAL": empty_bucket(),
    }
    by_trader_period: dict[tuple[str, str], dict] = defaultdict(empty_bucket)
    skipped_non_kzt = 0
    skipped_no_usd = 0

    for order in qs.iterator(chunk_size=500):
        trader_name = (
            order.payment_details.group.trader.user.username.strip().lower()
            if order.payment_details_id and order.payment_details.group_id and order.payment_details.group.trader_id
            else ""
        )
        if trader_name not in markups and trader_name not in traders:
            continue

        ps = order.solution.payment_system if order.solution_id else None
        cur = (ps.currency.symbol if ps and ps.currency_id else "") or ""
        ps_name = (ps.name if ps else "") or ""
        is_kzt = cur.upper() == "KZT" or "KZT" in ps_name.upper()
        if not is_kzt:
            skipped_non_kzt += 1
            continue

        amount = money(order.amount)
        usd = money(order.usd_amount)
        if amount <= 0 or usd <= 0:
            skipped_no_usd += 1
            continue

        merchant_markup = xe_kzt_markup_for_ps(ps_name) if ps_name else DEFAULT_XE_KZT_MARKUP
        psp_markup = markups.get(trader_name) or merchant_markup
        merchant_rate = getattr(order, "merchant_rate", None) or ZERO
        if money(merchant_rate) <= 0:
            merchant_rate = (amount / usd).quantize(Q3, rounding=ROUND_HALF_UP)

        expected_psp = expected_psp_usd(
            amount=amount,
            merchant_usd=usd,
            merchant_rate=merchant_rate,
            merchant_markup=merchant_markup,
            psp_markup=psp_markup,
        )
        stored_psp = money(order.psp_usd_amount)
        actual_psp = stored_psp if stored_psp > 0 else usd
        actual_fx = money(actual_psp - usd)
        expected_fx = money(expected_psp - usd)
        gap = money(expected_fx - actual_fx)
        has_dual = order_has_dual_fx(order)

        completed = order.completion_date.astimezone(MSK) if order.completion_date else None
        if dual_since is not None and completed is not None and completed < dual_since:
            period = "before_dual_fx"
        else:
            period = "on_after_dual_fx"

        for bucket in (
            by_trader[trader_name],
            by_period[period],
            by_period["TOTAL"],
            by_trader_period[(trader_name, period)],
        ):
            add_row(
                bucket,
                usd=usd,
                actual_psp=actual_psp,
                expected_psp=expected_psp,
                actual_fx=actual_fx,
                expected_fx=expected_fx,
                gap=gap,
                has_dual=has_dual,
            )

    if skipped_non_kzt or skipped_no_usd:
        print(f"\nskipped: non-KZT={skipped_non_kzt}  no amount/usd={skipped_no_usd}")

    print("\n" + "=" * 72)
    print("ПО ПРОВАЙДЕРУ (весь месяц)")
    print("=" * 72)
    for name in traders:
        print_bucket(name, by_trader[name])

    print("\n" + "=" * 72)
    print("ДО / ПОСЛЕ dual FX фикса")
    print("=" * 72)
    print_bucket("до dual FX (psp_usd обычно 0)", by_period["before_dual_fx"])
    print_bucket("с dual FX (день DUAL_FX_SINCE и после)", by_period["on_after_dual_fx"])
    print_bucket("ИТОГО месяц", by_period["TOTAL"])

    print("\n" + "=" * 72)
    print("ПРОВАЙДЕР × ПЕРИОД")
    print("=" * 72)
    for name in traders:
        for period in ("before_dual_fx", "on_after_dual_fx"):
            b = by_trader_period[(name, period)]
            if b["n"] == 0:
                continue
            print_bucket(f"{name} / {period}", b)

    total_gap = by_period["TOTAL"]["gap"]
    print("\n" + "=" * 72)
    print(f"СУММА РАСХОЖДЕНИЯ (expected FX − actual FX): {money_str(total_gap)} USDT")
    print("Это курсовой доход по условиям тетради, который не попал в кассу.")
    print("=" * 72)


run()
