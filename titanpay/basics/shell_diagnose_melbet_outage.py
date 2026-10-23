"""
Диагностика ночного простоя Melbet (выдача реквизитов) — особенно после deploy amount probe.

Ищет только Melbet redirect (pay_in с melbet_session). Для pandapay и др.:
  shell_diagnose_merchant_outage.py  (MERCHANT=pandapay)

Пример (последние 12 часов, melbet):
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_diagnose_melbet_outage.py

Ночное окно явно:
  docker compose exec -T \\
    -e SINCE='2026-08-21 20:00' \\
    -e UNTIL='2026-08-22 08:00' \\
    -e MERCHANT=melbet \\
    app python manage.py shell < titanpay/basics/shell_diagnose_melbet_outage.py

Сравнить с периодом после отката (контрольное окно той же длины):
  docker compose exec -T \\
    -e SINCE='2026-08-21 20:00' \\
    -e UNTIL='2026-08-22 08:00' \\
    -e COMPARE_SINCE='2026-08-22 08:00' \\
    app python manage.py shell < titanpay/basics/shell_diagnose_melbet_outage.py
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta

from django.utils import timezone

from merchant.kzt_settlement import melbet_kzt_usernames
from payments.models import (
    BitzonePayInSession,
    BotonpayPayInSession,
    PayIn,
    PayInTraceLog,
)
from payments.psp_payin import classify_payin_decline, psp_create_failure_reason_internal

HOURS = float(os.environ.get("HOURS", "12"))
MERCHANT = os.environ.get("MERCHANT", "").strip()
SINCE_RAW = os.environ.get("SINCE", "").strip()
UNTIL_RAW = os.environ.get("UNTIL", "").strip()
COMPARE_SINCE_RAW = os.environ.get("COMPARE_SINCE", "").strip()
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
    start = end - timedelta(hours=HOURS)
    return start, end


def _merchant_usernames() -> list[str]:
    if MERCHANT:
        return [MERCHANT]
    return sorted(melbet_kzt_usernames())


def _melbet_payins(start: datetime, end: datetime):
    usernames = _merchant_usernames()
    qs = (
        PayIn.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            melbet_session__isnull=False,
            merchant__user__username__in=usernames,
        )
        .select_related("status", "currency", "payment_system", "merchant__user", "order__status")
        .order_by("created_at")
    )
    return qs


def _routing_attempts(pay_in_ids: list) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in (
        PayInTraceLog.objects.filter(pay_in_id__in=pay_in_ids, direction="routing")
        .values_list("pay_in_id", flat=True)
    ):
        counts[str(row)] += 1
    return dict(counts)


def _probe_traces(pay_in_ids: list) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for log in PayInTraceLog.objects.filter(pay_in_id__in=pay_in_ids).order_by("created_at"):
        body = log.body if isinstance(log.body, dict) else {}
        if body.get("amount_probe") or "amount probe" in (log.note or "").lower():
            out[str(log.pay_in_id)] = body
    return out


def _routing_amounts(pay_in_id) -> list[str]:
    amounts: list[str] = []
    for log in PayInTraceLog.objects.filter(pay_in_id=pay_in_id, direction="routing").order_by("created_at"):
        body = log.body if isinstance(log.body, dict) else {}
        amt = body.get("amount")
        if amt is not None:
            amounts.append(str(amt))
    return amounts


def _psp_upstream_hint(pay_in: PayIn) -> str:
    for model in (BotonpayPayInSession, BitzonePayInSession):
        session = model.objects.filter(pay_in=pay_in).first()
        if session is None:
            continue
        cr = session.create_response or {}
        if not isinstance(cr, dict):
            continue
        err = cr.get("error") or cr.get("message") or cr.get("detail")
        if err:
            return f"{model.__name__}: {str(err)[:120]}"
        if cr.get("deal_uuid") or cr.get("id"):
            return f"{model.__name__}: deal_created"
    return ""


def _summarize_period(label: str, start: datetime, end: datetime) -> dict:
    payins = list(_melbet_payins(start, end))
    ids = [p.id for p in payins]
    routing_counts = _routing_attempts(ids)
    probe_map = _probe_traces(ids)

    status_counter = Counter((p.status.name if p.status else "?") for p in payins)
    inorder_counter = Counter(
        (p.order.status.name if p.order and p.order.status else "?") for p in payins
    )
    decline_codes = Counter()
    psp_notes = Counter()

    multi_routing = 0
    probe_suspects = 0
    routing_ok_but_declined = 0

    for p in payins:
        pid = str(p.id)
        attempts = routing_counts.get(pid, 0)
        if attempts > 1:
            multi_routing += 1
        if pid in probe_map:
            continue
        amounts = _routing_amounts(p.id)
        if len(set(amounts)) > 1:
            probe_suspects += 1

        if p.status and p.status.name == "Declined":
            decline_codes[classify_payin_decline(p)] += 1
            for log in PayInTraceLog.objects.filter(pay_in_id=p.id, direction="routing"):
                body = log.body if isinstance(log.body, dict) else {}
                if body.get("in_order_status") == "New" and body.get("payment_details_id"):
                    routing_ok_but_declined += 1
                    break
            for log in PayInTraceLog.objects.filter(pay_in_id=p.id, note__icontains="psp"):
                psp_notes[(log.note or "")[:80]] += 1

    total = len(payins)
    declined = status_counter.get("Declined", 0)
    success = status_counter.get("Success", 0)
    in_progress = status_counter.get("In Progress", 0)

    print("=" * 72)
    print(f"{label}")
    print(f"  window:   {start:%Y-%m-%d %H:%M %Z} .. {end:%Y-%m-%d %H:%M %Z}")
    print(f"  merchants: {', '.join(_merchant_usernames())}")
    print(f"  pay-ins:  {total}")
    if total:
        print(
            f"  status:   Success={success} ({success * 100 / total:.1f}%) | "
            f"Declined={declined} ({declined * 100 / total:.1f}%) | "
            f"In Progress={in_progress}"
        )
    print(f"  in_order: {dict(inorder_counter)}")
    print(f"  amount_probe traces: {len(probe_map)}")
    print(f"  multi routing attempts (>1 trace): {multi_routing}")
    print(f"  multiple amounts in routing traces: {probe_suspects}")
    print(f"  routing had trader/New but final Declined: {routing_ok_but_declined}")
    if decline_codes:
        print(f"  decline codes: {dict(decline_codes)}")
    if psp_notes:
        top = psp_notes.most_common(5)
        print(f"  psp trace notes (top): {top}")

    declined_payins = [p for p in payins if p.status and p.status.name == "Declined"]
    if declined_payins:
        print(f"\n  --- sample Declined (max {SAMPLE}) ---")
        for p in declined_payins[:SAMPLE]:
            amounts = _routing_amounts(p.id)
            attempts = routing_counts.get(str(p.id), 0)
            print(
                f"  pay_in={p.id} order={p.merchant_order_id} "
                f"amount={p.amount} ps={p.payment_system.name if p.payment_system else '?'}"
            )
            print(
                f"    in_order={p.order.status.name if p.order and p.order.status else '?'} | "
                f"routing_attempts={attempts} | amounts_tried={amounts or ['?']}"
            )
            print(f"    reason: {psp_create_failure_reason_internal(p)}")
            hint = _psp_upstream_hint(p)
            if hint:
                print(f"    psp: {hint}")

    return {
        "total": total,
        "declined": declined,
        "success": success,
        "multi_routing": multi_routing,
        "probe_suspects": probe_suspects,
        "routing_ok_but_declined": routing_ok_but_declined,
    }


def _interpret(bad: dict, good: dict | None) -> None:
    print("\n" + "=" * 72)
    print("INTERPRETATION")
    if bad["total"] == 0:
        print("  No melbet pay-ins in the bad window — widen SINCE/UNTIL or check MERCHANT.")
        return

    decline_rate = bad["declined"] * 100 / bad["total"] if bad["total"] else 0
    if bad["multi_routing"] > bad["total"] * 0.3 or bad["probe_suspects"] > 0:
        print(
            "  [!] Amount probe likely ACTIVE: many pay-ins have multiple routing attempts "
            "or different amounts in traces."
        )
        print(
            "      Typical failure mode: first PSP attach succeeds but probe loop continues, "
            "cancels deal and tries other amounts → all fail."
        )
        print("      Fix: disable MELBET_AMOUNT_PROBE_ENABLED or deploy fixed probe logic.")

    if bad["routing_ok_but_declined"] > bad["declined"] * 0.2:
        print(
            "  [!] Routing/PSP once assigned trader (New + payment_details) but pay-in ended Declined."
        )
        print("      Strong signal of amount_probe reallocate() cancelling a working PSP session.")

    if bad["declined"] and decline_rate > 80:
        print(f"  [!] Very high decline rate ({decline_rate:.0f}%) — systemic, not random PSP noise.")

    print(
        "  Check: docker compose exec app python manage.py analyze_merchant_rejects "
        f"--merchant {MERCHANT or 'melbet'} --hours {HOURS}"
    )
    print(
        "  Single pay-in: docker compose exec app python manage.py diagnose_payin <pay_in_uuid>"
    )

    if good and good.get("total"):
        bad_dr = bad["declined"] * 100 / bad["total"] if bad["total"] else 0
        good_dr = good["declined"] * 100 / good["total"] if good["total"] else 0
        print(f"\n  Compare decline rate: bad={bad_dr:.1f}% vs after_rollback={good_dr:.1f}%")
        if good_dr < bad_dr - 20:
            print("  => Strong correlation: outage ended after rollback to pre-probe version.")


def main() -> None:
    start, end = _window()
    bad = _summarize_period("MELBET OUTAGE WINDOW", start, end)

    good = None
    if COMPARE_SINCE_RAW:
        compare_start = _parse_dt(COMPARE_SINCE_RAW)
        duration = end - start
        compare_end = compare_start + duration
        good = _summarize_period("AFTER ROLLBACK (control window)", compare_start, compare_end)

    _interpret(bad, good)


main()
