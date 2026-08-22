"""
Диагностика простоя выдачи реквизитов для ЛЮБОГО мерчанта (pandapay, melbet, …).

Не путать с shell_diagnose_melbet_outage.py — тот только Melbet redirect (melbet_session).

Пример — ночь pandapay:
  docker compose exec -T \\
    -e MERCHANT=pandapay \\
    -e SINCE='2026-08-21 20:00' \\
    -e UNTIL='2026-08-22 08:00' \\
    app python manage.py shell < titanpay/basics/shell_diagnose_merchant_outage.py

Сравнение с периодом после отката:
  docker compose exec -T \\
    -e MERCHANT=pandapay \\
    -e SINCE='2026-08-21 20:00' \\
    -e UNTIL='2026-08-22 08:00' \\
    -e COMPARE_SINCE='2026-08-22 08:00' \\
    app python manage.py shell < titanpay/basics/shell_diagnose_merchant_outage.py

Последние N часов:
  docker compose exec -T -e MERCHANT=pandapay -e HOURS=12 \\
    app python manage.py shell < titanpay/basics/shell_diagnose_merchant_outage.py
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.db.models import Count
from django.utils import timezone

from merchant.models import Merchant
from payments.models import PayIn, PayInTraceLog
from payments.psp_payin import classify_payin_decline, is_psp_trader, psp_create_failure_reason_internal
from trade.models import InOrder

HOURS = float(os.environ.get("HOURS", "12"))
MERCHANT_RAW = os.environ.get("MERCHANT", "pandapay").strip()
SINCE_RAW = os.environ.get("SINCE", "").strip()
UNTIL_RAW = os.environ.get("UNTIL", "").strip()
COMPARE_SINCE_RAW = os.environ.get("COMPARE_SINCE", "").strip()
PS_FILTER = os.environ.get("PS", "").strip()
SAMPLE = int(os.environ.get("SAMPLE", "8"))


def _parse_dt(raw: str) -> datetime:
    raw = raw.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(raw, fmt)
            if timezone.is_naive(dt):
                return timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {raw!r}")


def _window() -> tuple[datetime, datetime]:
    if SINCE_RAW:
        start = _parse_dt(SINCE_RAW)
        end = _parse_dt(UNTIL_RAW) if UNTIL_RAW else timezone.now()
        return start, end
    end = timezone.now()
    return end - timedelta(hours=HOURS), end


def _resolve_merchant_username(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("MERCHANT is required, e.g. MERCHANT=pandapay")

    if Merchant.objects.filter(user__username__iexact=raw).exists():
        return User.objects.get(username__iexact=raw).username

    partial = list(
        Merchant.objects.filter(user__username__icontains=raw)
        .values_list("user__username", flat=True)[:10]
    )
    if len(partial) == 1:
        print(f"  note: resolved MERCHANT={raw!r} -> {partial[0]!r}")
        return partial[0]

    if partial:
        raise ValueError(
            f"Merchant {raw!r} not found. Did you mean one of: {', '.join(partial)}? "
            "(pandapay1 is usually a trader, merchant is pandapay)"
        )
    raise ValueError(f"Merchant {raw!r} not found in DB")


def _payins(merchant: str, start: datetime, end: datetime):
    qs = PayIn.objects.filter(
        created_at__gte=start,
        created_at__lt=end,
        merchant__user__username=merchant,
    ).select_related("status", "payment_system", "order__status", "order__payment_details__group__trader__user")
    if PS_FILTER:
        qs = qs.filter(payment_system__name__iexact=PS_FILTER)
    return qs.order_by("created_at")


def _inorders(merchant: str, start: datetime, end: datetime):
    qs = InOrder.objects.filter(
        creation_date__gte=start,
        creation_date__lt=end,
        solution__merchant__user__username=merchant,
    ).select_related("status", "solution__payment_system", "payment_details__group__trader__user")
    if PS_FILTER:
        qs = qs.filter(solution__payment_system__name__iexact=PS_FILTER)
    return qs


def _trader_is_psp(in_order: InOrder) -> bool:
    if not in_order.payment_details_id:
        return False
    return is_psp_trader(in_order.payment_details.group.trader)


def _print_conversion(payins, in_orders) -> dict:
    total = payins.count()
    declined = payins.filter(status__name="Declined").count()
    success = payins.filter(status__name="Success").count()
    in_progress = payins.filter(status__name="In Progress").count()
    issued = total - declined

    print("\n=== КОНВЕРСИЯ PAY-IN (когорта created_at) ===")
    print(f"  Создано: {total}")
    print(f"  Declined (без рек): {declined}")
    print(f"  Выдан рек (не Declined): {issued}")
    print(f"  Success: {success}")
    print(f"  In Progress: {in_progress}")
    if issued:
        print(f"  Конверсия рек → Success: {100 * success / issued:.1f}%")
    if total:
        print(f"  Конверсия create → Success: {100 * success / total:.1f}%")

    assigned_psp = assigned_local = completed_psp = completed_local = 0
    for o in in_orders.filter(payment_details__isnull=False):
        if _trader_is_psp(o):
            assigned_psp += 1
            if o.status and o.status.name == "Completed":
                completed_psp += 1
        else:
            assigned_local += 1
            if o.status and o.status.name == "Completed":
                completed_local += 1

    print("\n=== КОНВЕРСИЯ IN-ORDER (назначены реквизиты) ===")
    print(f"  PSP трейдеры: назначено={assigned_psp}, Completed={completed_psp}", end="")
    if assigned_psp:
        print(f", conv={100 * completed_psp / assigned_psp:.1f}%")
    else:
        print()
    print(f"  Локальные трейдеры: назначено={assigned_local}, Completed={completed_local}", end="")
    if assigned_local:
        print(f", conv={100 * completed_local / assigned_local:.1f}%")
    else:
        print()

    cannot = in_orders.filter(status__name="Cannot process").count()
    print(f"\n  InOrder Cannot process: {cannot}")

    return {
        "total": total,
        "declined": declined,
        "success": success,
        "issued": issued,
        "cannot_process": cannot,
        "assigned_psp": assigned_psp,
        "assigned_local": assigned_local,
    }


def _summarize(label: str, merchant: str, start: datetime, end: datetime) -> dict:
    payins = _payins(merchant, start, end)
    in_orders = _inorders(merchant, start, end)
    ids = list(payins.values_list("id", flat=True))

    status_counter = Counter(payins.values_list("status__name", flat=True))
    ps_counter = Counter(
        payins.values_list("payment_system__name", flat=True)
    )
    inorder_counter = Counter(in_orders.values_list("status__name", flat=True))

    decline_codes = Counter()
    for p in payins.filter(status__name="Declined")[:500]:
        decline_codes[classify_payin_decline(p)] += 1

    psp_fail_notes = Counter()
    for log in PayInTraceLog.objects.filter(
        pay_in_id__in=ids,
        note__icontains="psp",
    ):
        psp_fail_notes[(log.note or "")[:100]] += 1

    routing_multi = Counter()
    for pid, cnt in (
        PayInTraceLog.objects.filter(pay_in_id__in=ids, direction="routing")
        .values("pay_in_id")
        .annotate(n=Count("id"))
        .values_list("pay_in_id", "n")
    ):
        if cnt > 1:
            routing_multi[str(pid)] = cnt

    print("=" * 72)
    print(label)
    print(f"  merchant: {merchant}")
    print(f"  window:   {start:%Y-%m-%d %H:%M %Z} .. {end:%Y-%m-%d %H:%M %Z}")
    if PS_FILTER:
        print(f"  payment_system filter: {PS_FILTER}")
    print(f"  pay-ins:  {payins.count()}")
    print(f"  pay-in status: {dict(status_counter)}")
    print(f"  by payment_system: {dict(ps_counter)}")
    print(f"  in-order status: {dict(inorder_counter)}")
    if decline_codes:
        print(f"  decline codes: {dict(decline_codes)}")
    if psp_fail_notes:
        print(f"  psp fail traces (top 5): {psp_fail_notes.most_common(5)}")
    if routing_multi:
        print(f"  pay-ins with >1 routing trace: {len(routing_multi)} (melbet amount probe only)")

    stats = _print_conversion(payins, in_orders)

    declined_list = list(payins.filter(status__name="Declined")[:SAMPLE])
    if declined_list:
        print(f"\n=== SAMPLE Declined (max {SAMPLE}) ===")
        for p in declined_list:
            trader = None
            if p.order and p.order.payment_details_id:
                trader = p.order.payment_details.group.trader.user.username
            print(
                f"  {p.created_at:%m-%d %H:%M} pay_in={p.id} "
                f"order={p.merchant_order_id} amount={p.amount} "
                f"ps={p.payment_system.name if p.payment_system else '?'} "
                f"in_order={p.order.status.name if p.order and p.order.status else '?'}"
            )
            print(f"    trader={trader} | {psp_create_failure_reason_internal(p)}")

    return {**stats, "routing_multi": len(routing_multi)}


def _interpret(bad: dict, good: dict | None, merchant: str) -> None:
    print("\n" + "=" * 72)
    print("INTERPRETATION")

    if bad["total"] == 0:
        print("  No pay-ins in window.")
        print(f"  Check merchant username (use pandapay, not pandapay1).")
        print(f"  List merchants: Merchant.objects.filter(user__username__icontains='panda')")
        return

    decline_rate = 100 * bad["declined"] / bad["total"] if bad["total"] else 0
    if decline_rate > 50:
        print(f"  [!] High decline rate {decline_rate:.0f}% — реквизиты не выдавались в основном на create.")

    if bad["cannot_process"] > bad["total"] * 0.3:
        print("  [!] Много InOrder Cannot process — роутинг или PSP API не дали реквизиты.")

    if bad["assigned_psp"] == 0 and bad["declined"] > 0:
        print("  [!] Ни одного PSP-назначения — проверьте routing (diagnose_routing), активность групп PSP.")

    if bad["routing_multi"] > 0:
        print("  [!] Multiple routing traces — только melbet amount probe; для pandapay не должно быть.")

    if good and good["total"] > 0:
        bad_dr = 100 * bad["declined"] / bad["total"]
        good_dr = 100 * good["declined"] / good["total"]
        bad_issued = bad["issued"] or 1
        good_issued = good["issued"] or 1
        bad_succ = 100 * bad["success"] / bad_issued
        good_succ = 100 * good["success"] / good_issued
        print(f"\n  Compare:")
        print(f"    decline rate:  {bad_dr:.1f}% -> {good_dr:.1f}%")
        print(f"    issued (рек):  {bad['issued']} -> {good['issued']}")
        print(f"    success/issued:{bad_succ:.1f}% -> {good_succ:.1f}%")
        if good_dr < bad_dr - 15 or good["issued"] > bad["issued"] * 1.5:
            print("  => Outage correlates with rollback window (выдача восстановилась).")

    print(f"\n  More: python manage.py analyze_merchant_rejects --merchant {merchant} --hours 12")
    print(f"       python manage.py analyze_cannot_process --merchant {merchant} --hours 12")
    print(f"       python manage.py diagnose_payin <uuid>")


def main() -> None:
    merchant = _resolve_merchant_username(MERCHANT_RAW)
    start, end = _window()
    bad = _summarize("MERCHANT OUTAGE WINDOW", merchant, start, end)

    good = None
    if COMPARE_SINCE_RAW:
        compare_start = _parse_dt(COMPARE_SINCE_RAW)
        duration = end - start
        good = _summarize("AFTER ROLLBACK (control)", merchant, compare_start, compare_start + duration)

    _interpret(bad, good, merchant)


main()
