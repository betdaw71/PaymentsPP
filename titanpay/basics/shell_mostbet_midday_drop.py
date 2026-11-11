"""Разбор спада конверсии Mostbet днём (типично 12–14 MSK) — вчера vs сегодня.

Почасовая таблица + zoom 12–14: PSP, причины Declined, fail traces.

  # вчера + сегодня по часам (МСК)
  docker compose exec -T -e MERCHANT=mostbet app python manage.py shell \\
    < titanpay/basics/shell_mostbet_midday_drop.py

  # только окна 12–14 двух дней
  docker compose exec -T -e MERCHANT=mostbet -e FOCUS=1 app python manage.py shell \\
    < titanpay/basics/shell_mostbet_midday_drop.py

  DAYS=2 HOUR_FROM=12 HOUR_TO=14 PS=C2CKZT
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from payments.models import PayIn, PayInTraceLog
from payments.psp_payin import classify_payin_decline

MSK = ZoneInfo("Europe/Moscow")
MERCHANT = (os.environ.get("MERCHANT") or "mostbet").strip()
PS = (os.environ.get("PS") or "").strip()
DAYS = max(1, int(os.environ.get("DAYS") or "2"))
HOUR_FROM = int(os.environ.get("HOUR_FROM") or "12")
HOUR_TO = int(os.environ.get("HOUR_TO") or "14")  # exclusive end hour bound → 12..13 if 14
FOCUS = (os.environ.get("FOCUS") or "").strip().lower() in {"1", "true", "yes", "on"}
SAMPLE = int(os.environ.get("SAMPLE") or "12")


def _now():
    return timezone.now().astimezone(MSK)


def _floor_hour(dt: datetime) -> datetime:
    dt = dt.astimezone(MSK)
    return dt.replace(minute=0, second=0, microsecond=0)


def provider_of(pay_in) -> str:
    order = pay_in.order
    if order is None or not order.payment_details_id:
        return "(no_req)"
    try:
        return order.payment_details.group.trader.user.username or "(no_trader)"
    except Exception:  # noqa: BLE001
        return "(no_trader)"


def pct(n, d) -> str:
    if d <= 0:
        return "  -  "
    return f"{100.0 * n / d:5.1f}%"


def analyze_window(label: str, start: datetime, end: datetime) -> None:
    qs = PayIn.objects.filter(
        merchant__user__username=MERCHANT,
        created_at__gte=start,
        created_at__lt=end,
    ).select_related(
        "status",
        "payment_system",
        "order__status",
        "order__payment_details__group__trader__user",
    )
    if PS:
        qs = qs.filter(payment_system__name__iexact=PS)

    rows = list(qs.order_by("created_at"))
    created = len(rows)
    declined = sum(1 for p in rows if p.status and p.status.name == "Declined")
    success = sum(1 for p in rows if p.status and p.status.name == "Success")
    progress = sum(1 for p in rows if p.status and p.status.name in {"In Progress", "Pending"})
    issued = created - declined

    print(f"\n=== {label}  {start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%H:%M %Z')} ===")
    print(
        f"  create={created}  declined={declined}  issued={issued}  "
        f"success={success}  progress={progress}"
    )
    print(
        f"  cr→ok={pct(success, created)}  iss→ok={pct(success, issued)}  "
        f"declined%={pct(declined, created)}"
    )

    by_psp = defaultdict(lambda: Counter())
    decline_reasons = Counter()
    for p in rows:
        st = p.status.name if p.status else "-"
        psp = provider_of(p)
        by_psp[psp][st] += 1
        by_psp[psp]["n"] += 1
        if st == "Declined":
            try:
                reason = classify_payin_decline(p) or "unknown"
            except Exception:  # noqa: BLE001
                reason = "classify_error"
            decline_reasons[str(reason)[:80]] += 1

    if by_psp:
        print("  by PSP:")
        for psp, c in sorted(by_psp.items(), key=lambda x: -x[1]["n"]):
            n = c["n"]
            ok = c.get("Success", 0)
            dec = c.get("Declined", 0)
            iss = n - dec
            print(
                f"    {psp:16} n={n:4}  declined={dec:3}  success={ok:3}  "
                f"iss→ok={pct(ok, iss)}  cr→ok={pct(ok, n)}"
            )

    if decline_reasons:
        print("  decline reasons (top):")
        for reason, n in decline_reasons.most_common(8):
            print(f"    {n:4}  {reason}")

    # routing / PSP fail traces in window
    fail_notes = Counter()
    traces = PayInTraceLog.objects.filter(
        pay_in__merchant__user__username=MERCHANT,
        created_at__gte=start,
        created_at__lt=end,
        direction="routing",
    )
    if PS:
        traces = traces.filter(pay_in__payment_system__name__iexact=PS)
    for note in traces.values_list("note", flat=True).iterator(chunk_size=500):
        n = (note or "").strip()
        if not n:
            continue
        low = n.lower()
        if any(k in low for k in ("fail", "cannot", "no_session", "reject", "error", "unavailable")):
            fail_notes[n[:100]] += 1
    if fail_notes:
        print("  routing fail-ish notes (top):")
        for note, n in fail_notes.most_common(8):
            print(f"    {n:4}  {note}")

    # sample declined
    declined_rows = [p for p in rows if p.status and p.status.name == "Declined"][:SAMPLE]
    if declined_rows:
        print(f"  sample Declined (up to {SAMPLE}):")
        for p in declined_rows:
            try:
                reason = classify_payin_decline(p) or "-"
            except Exception:  # noqa: BLE001
                reason = "-"
            print(
                f"    {p.created_at.astimezone(MSK).strftime('%H:%M:%S')}  "
                f"id={p.id}  amount={p.amount}  ps={getattr(p.payment_system, 'name', None)}  "
                f"psp={provider_of(p)}  reason={reason}"
            )


def hourly_table(day_start: datetime) -> None:
    day_end = day_start + timedelta(days=1)
    print(f"\n--- hourly {day_start.strftime('%Y-%m-%d')} MSK  merchant={MERCHANT} ---")
    print(f"{'hour':>5}  {'create':>6}  {'decl':>5}  {'iss':>5}  {'ok':>5}  {'cr→ok':>6}  {'iss→ok':>6}")
    for h in range(24):
        start = day_start + timedelta(hours=h)
        end = start + timedelta(hours=1)
        if start >= _now():
            break
        qs = PayIn.objects.filter(
            merchant__user__username=MERCHANT,
            created_at__gte=start,
            created_at__lt=end,
        )
        if PS:
            qs = qs.filter(payment_system__name__iexact=PS)
        created = qs.count()
        if created == 0:
            mark = " ◀" if HOUR_FROM <= h < HOUR_TO else ""
            print(f"  {h:02d}    {0:6}  {0:5}  {0:5}  {0:5}  {'  -  ':>6}  {'  -  ':>6}{mark}")
            continue
        declined = qs.filter(status__name="Declined").count()
        success = qs.filter(status__name="Success").count()
        issued = created - declined
        mark = " ◀ focus" if HOUR_FROM <= h < HOUR_TO else ""
        print(
            f"  {h:02d}    {created:6}  {declined:5}  {issued:5}  {success:5}  "
            f"{pct(success, created):>6}  {pct(success, issued):>6}{mark}"
        )


def run() -> None:
    now = _now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    print("=" * 72)
    print(f"MOSTBET MIDDAY DROP  merchant={MERCHANT}  now={now.isoformat()}")
    print(f"  focus hours MSK: {HOUR_FROM:02d}:00–{HOUR_TO:02d}:00  PS={PS or 'ALL'}  DAYS={DAYS}")
    print("=" * 72)

    days = []
    for i in range(DAYS - 1, -1, -1):
        days.append(today - timedelta(days=i))

    if not FOCUS:
        for day in days:
            hourly_table(day)

    for day in days:
        start = day + timedelta(hours=HOUR_FROM)
        end = day + timedelta(hours=HOUR_TO)
        if start >= now:
            continue
        end = min(end, now)
        analyze_window(f"FOCUS {day.strftime('%Y-%m-%d')} {HOUR_FROM:02d}-{HOUR_TO:02d}", start, end)

    # baseline: same length window morning 09-11 for comparison
    for day in days:
        start = day + timedelta(hours=9)
        end = day + timedelta(hours=11)
        if start >= now:
            continue
        end = min(end, now)
        if end <= start:
            continue
        analyze_window(f"BASELINE {day.strftime('%Y-%m-%d')} 09-11", start, end)

    print("\nDONE")


run()
