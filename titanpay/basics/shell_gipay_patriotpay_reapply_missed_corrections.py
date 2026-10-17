"""
GiPay / PatriotPay: Completed-заявки, где повторный success с новой суммой
принят как idempotent, а сумма и колбек мерчанту не ушли.

Берёт last_webhook_payload и свежие trace webhook. По умолчанию DRY_RUN.
APPLY=1 — handle_psp_success_webhook (пересчёт + колбек).

  docker compose exec -T app \\
    python manage.py shell < titanpay/basics/shell_gipay_patriotpay_reapply_missed_corrections.py

  docker compose exec -T -e DAYS=14 app \\
    python manage.py shell < titanpay/basics/shell_gipay_patriotpay_reapply_missed_corrections.py

  docker compose exec -T -e APPLY=1 app \\
    python manage.py shell < titanpay/basics/shell_gipay_patriotpay_reapply_missed_corrections.py

Одна заявка:
  docker compose exec -T -e PAY_IN_ID=<uuid> -e APPLY=1 app \\
    python manage.py shell < titanpay/basics/shell_gipay_patriotpay_reapply_missed_corrections.py
"""
from __future__ import annotations

import json
import os
import traceback
from collections import Counter
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from payments.gipay_client import gipay_webhook_outcome
from payments.models import GipayPayInSession, PayInTraceLog, PatriotpayPayInSession
from payments.patriotpay_client import patriotpay_webhook_outcome
from payments.psp_payin import handle_psp_success_webhook, parse_psp_webhook_paid_amount
from trade.models import InOrder

Q2 = Decimal("0.01")


def q2(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _payload_dict(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _best_success_body(pay_in, session, *, direction: str, outcome_fn):
    current = q2(pay_in.order.amount)
    bodies: list[dict] = []
    last = _payload_dict(session.last_webhook_payload)
    if last:
        bodies.append(last)
    traces = PayInTraceLog.objects.filter(pay_in=pay_in, direction=direction).order_by("-created_at")[:30]
    for item in traces:
        body = _payload_dict(item.body)
        if body:
            bodies.append(body)

    matched = None
    for body in bodies:
        if outcome_fn(body) != "success":
            continue
        paid = parse_psp_webhook_paid_amount(body)
        if paid is None:
            continue
        paid = q2(paid)
        if paid != current:
            return body, paid
        if matched is None:
            matched = (body, paid)
    if matched:
        return matched
    return None, None


def _scan(label: str, qs, *, direction: str, outcome_fn, only_completed: bool):
    planned = []
    stats = Counter()
    scanned = 0
    for session in qs.iterator(chunk_size=200):
        scanned += 1
        pay_in = session.pay_in
        order = pay_in.order if pay_in else None
        if order is None:
            stats["no_order"] += 1
            continue
        last = _payload_dict(session.last_webhook_payload)
        body, paid = _best_success_body(pay_in, session, direction=direction, outcome_fn=outcome_fn)
        if body is None or paid is None:
            if not last:
                stats["empty_last_webhook"] += 1
            elif outcome_fn(last) != "success":
                stats[f"last_outcome={outcome_fn(last)}"] += 1
            else:
                stats["success_but_no_parsed_amount"] += 1
            continue
        status = order.status.name if order.status_id else "-"
        if only_completed and status != "Completed":
            stats[f"status={status}"] += 1
            continue
        old_amount = q2(order.amount)
        if old_amount == paid:
            stats["amount_already_matches"] += 1
            continue
        merchant = "-"
        try:
            merchant = order.solution.merchant.user.username
        except Exception:  # noqa: BLE001
            pass
        planned.append(
            {
                "psp": label,
                "pay_in": str(pay_in.id),
                "moid": pay_in.merchant_order_id or "",
                "status": status,
                "merchant": merchant,
                "old": old_amount,
                "paid": paid,
                "delta": q2(paid - old_amount),
                "recalculated": bool(order.recalculated),
                "order_id": order.id,
                "body": body,
            }
        )
    return scanned, planned, stats


def run() -> None:
    apply = env_flag("APPLY", False)
    days = int((os.environ.get("DAYS") or "14").strip() or "14")
    pay_in_id = (os.environ.get("PAY_IN_ID") or "").strip()
    only_completed = env_flag("ONLY_COMPLETED", True)
    since = timezone.now() - timedelta(days=days)

    gipay = GipayPayInSession.objects.select_related(
        "pay_in", "pay_in__order", "pay_in__order__status", "pay_in__order__solution__merchant__user"
    ).filter(pay_in__isnull=False, pay_in__order__isnull=False)
    patriot = PatriotpayPayInSession.objects.select_related(
        "pay_in", "pay_in__order", "pay_in__order__status", "pay_in__order__solution__merchant__user"
    ).filter(pay_in__isnull=False, pay_in__order__isnull=False)
    if pay_in_id:
        gipay = gipay.filter(pay_in_id=pay_in_id)
        patriot = patriot.filter(pay_in_id=pay_in_id)
    else:
        gipay = gipay.filter(updated_at__gte=since)
        patriot = patriot.filter(updated_at__gte=since)

    print(
        f"mode={'APPLY' if apply else 'DRY_RUN'}  DAYS={days}  "
        f"since={since.isoformat()}  PAY_IN_ID={pay_in_id or '-'}"
    )
    print()

    scanned_g, planned_g, stats_g = _scan(
        "gipay", gipay, direction="gipay_webhook", outcome_fn=gipay_webhook_outcome,
        only_completed=only_completed,
    )
    scanned_p, planned_p, stats_p = _scan(
        "patriotpay", patriot, direction="patriotpay_webhook", outcome_fn=patriotpay_webhook_outcome,
        only_completed=only_completed,
    )
    planned = planned_g + planned_p

    print(f"scanned gipay={scanned_g} patriotpay={scanned_p}")
    print(f"need recalc: {len(planned)}")
    print("gipay skip:", dict(stats_g))
    print("patriotpay skip:", dict(stats_p))
    if planned:
        total_delta = q2(sum((row["delta"] for row in planned), Decimal("0")))
        print(f"sum delta (paid - current): {total_delta}")
        print()
        print(f"{'psp':10} {'pay_in':36} {'moid':16} {'old':>10} {'paid':>10} {'delta':>10} recalc merchant")
        for row in planned:
            print(
                f"{row['psp']:10} {row['pay_in']} {row['moid'][:16]:16} "
                f"{row['old']:10} {row['paid']:10} {row['delta']:10} "
                f"{int(row['recalculated'])} {row['merchant']}"
            )

    if not apply:
        print()
        print("DRY_RUN — деньги и колбеки не трогали. Для применения: -e APPLY=1")
        return

    print()
    print("APPLY…")
    ok = 0
    failed = 0
    for row in planned:
        try:
            with transaction.atomic():
                order = InOrder.objects.select_for_update().get(pk=row["order_id"])
                outcome = handle_psp_success_webhook(order, row["body"])
            print(f"APPLY {row['psp']} {row['pay_in']} {row['old']} -> {row['paid']} outcome={outcome}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {row['pay_in']}: {exc}")
            traceback.print_exc()
    print(f"\nAPPLY done ok={ok} fail={failed}")


run()
