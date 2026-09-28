"""
Bitzone / VisionX: Completed-заявки, где повторный success с новой суммой
принят как idempotent (как старый баг PayPlat), а сумма на сайте не обновилась.

По умолчанию DRY_RUN. APPLY=1 — handle_psp_success_webhook.

  docker compose exec -T app \\
    python manage.py shell < titanpay/basics/shell_bitzone_visionx_reapply_missed_corrections.py

  docker compose exec -T -e DAYS=14 app \\
    python manage.py shell < titanpay/basics/shell_bitzone_visionx_reapply_missed_corrections.py

  docker compose exec -T -e APPLY=1 app \\
    python manage.py shell < titanpay/basics/shell_bitzone_visionx_reapply_missed_corrections.py

Одна заявка:
  docker compose exec -T -e PAY_IN_ID=<uuid> -e APPLY=1 app \\
    python manage.py shell < titanpay/basics/shell_bitzone_visionx_reapply_missed_corrections.py
"""
from __future__ import annotations

import os
import traceback
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from payments.bitzone_client import bitzone_webhook_outcome
from payments.models import BitzonePayInSession, PayInTraceLog, VisionxPayInSession
from payments.psp_payin import handle_psp_success_webhook, parse_psp_webhook_paid_amount
from payments.visionx_client import visionx_webhook_outcome
from trade.models import InOrder

Q2 = Decimal("0.01")


def q2(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _best_success_body(pay_in, session, *, direction: str, outcome_fn):
    current = q2(pay_in.order.amount)
    bodies: list[dict] = []
    last = session.last_webhook_payload if isinstance(session.last_webhook_payload, dict) else {}
    if last:
        bodies.append(last)
    traces = (
        PayInTraceLog.objects.filter(pay_in=pay_in, direction=direction)
        .order_by("-created_at")[:30]
    )
    for t in traces:
        if isinstance(t.body, dict) and t.body:
            bodies.append(t.body)

    for body in bodies:
        if outcome_fn(body) != "success":
            continue
        paid = parse_psp_webhook_paid_amount(body)
        if paid is None:
            continue
        paid = q2(paid)
        if paid != current:
            return body, paid
    return None, None


def _scan(label: str, qs, *, direction: str, outcome_fn, apply: bool, only_completed: bool):
    planned = []
    skipped = []
    scanned = 0
    for session in qs.iterator(chunk_size=200):
        scanned += 1
        pay_in = session.pay_in
        order = pay_in.order if pay_in else None
        if order is None:
            continue
        body, paid = _best_success_body(pay_in, session, direction=direction, outcome_fn=outcome_fn)
        if body is None or paid is None:
            skipped.append((str(pay_in.id), f"{label}: no success amount"))
            continue
        status = order.status.name if order.status_id else "-"
        if only_completed and status != "Completed":
            skipped.append((str(pay_in.id), f"status={status}"))
            continue
        old_amount = q2(order.amount)
        if old_amount == paid:
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
    return scanned, planned, skipped


def run() -> None:
    apply = env_flag("APPLY", False)
    days = int((os.environ.get("DAYS") or "14").strip() or "14")
    pay_in_id = (os.environ.get("PAY_IN_ID") or "").strip()
    only_completed = env_flag("ONLY_COMPLETED", True)
    since = timezone.now() - timedelta(days=days)

    bz = BitzonePayInSession.objects.select_related(
        "pay_in", "pay_in__order", "pay_in__order__status", "pay_in__order__solution__merchant__user"
    ).filter(pay_in__isnull=False, pay_in__order__isnull=False)
    vx = VisionxPayInSession.objects.select_related(
        "pay_in", "pay_in__order", "pay_in__order__status", "pay_in__order__solution__merchant__user"
    ).filter(pay_in__isnull=False, pay_in__order__isnull=False)
    if pay_in_id:
        bz = bz.filter(pay_in_id=pay_in_id)
        vx = vx.filter(pay_in_id=pay_in_id)
    else:
        bz = bz.filter(updated_at__gte=since)
        vx = vx.filter(updated_at__gte=since)

    print(f"mode={'APPLY' if apply else 'DRY_RUN'}  DAYS={days}  since={since.isoformat()}  PAY_IN_ID={pay_in_id or '-'}")
    print()

    scanned_bz, planned_bz, skip_bz = _scan(
        "bitzone", bz, direction="bitzone_webhook", outcome_fn=bitzone_webhook_outcome,
        apply=apply, only_completed=only_completed,
    )
    scanned_vx, planned_vx, skip_vx = _scan(
        "visionx", vx, direction="visionx_webhook", outcome_fn=visionx_webhook_outcome,
        apply=apply, only_completed=only_completed,
    )
    planned = planned_bz + planned_vx

    print(f"scanned bitzone={scanned_bz} visionx={scanned_vx}")
    print(f"need recalc: {len(planned)}")
    if planned:
        print()
        print(f"{'psp':8} {'pay_in':36} {'moid':16} {'old':>10} {'paid':>10} {'delta':>10} recalc merchant")
        for row in planned:
            print(
                f"{row['psp']:8} {row['pay_in']} {row['moid'][:16]:16} "
                f"{row['old']:10} {row['paid']:10} {row['delta']:10} "
                f"{int(row['recalculated'])} {row['merchant']}"
            )

    if not apply:
        print("\nDRY_RUN. Применить: docker compose exec -T -e APPLY=1 app python manage.py shell < titanpay/basics/shell_bitzone_visionx_reapply_missed_corrections.py")
        return

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
