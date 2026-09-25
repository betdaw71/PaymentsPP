"""
PayPlat: найти Completed-заявки, где повторный SUCCESS с новым quote_amount
принят (HTTP 200), но сумма на сайте не обновилась (баг early-return).

По умолчанию DRY_RUN — только список. APPLY=1 — пересчёт через
handle_psp_success_webhook внутри transaction.atomic().

Окно: DAYS=7 (по умолчанию) — по PayplatPayInSession.updated_at.

Запуск плана (ничего не меняет):
  docker compose exec -T app \\
    python manage.py shell < titanpay/basics/shell_payplat_reapply_missed_corrections.py

  docker compose exec -T -e DAYS=7 app \\
    python manage.py shell < titanpay/basics/shell_payplat_reapply_missed_corrections.py

Применить после ревью плана:
  docker compose exec -T -e APPLY=1 app \\
    python manage.py shell < titanpay/basics/shell_payplat_reapply_missed_corrections.py

Одна заявка:
  docker compose exec -T \\
    -e PAY_IN_ID=36ac9db1-b99c-4ca1-8e8e-1a810cbb59b4 -e APPLY=1 app \\
    python manage.py shell < titanpay/basics/shell_payplat_reapply_missed_corrections.py
"""
from __future__ import annotations

import os
import traceback
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from payments.models import PayplatPayInSession
from payments.payplat_client import payplat_webhook_outcome, payplat_webhook_paid_amount
from payments.psp_payin import handle_psp_success_webhook
from trade.models import InOrder

Q2 = Decimal("0.01")


def q2(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def run() -> None:
    apply = env_flag("APPLY", False)
    days = int((os.environ.get("DAYS") or "7").strip() or "7")
    pay_in_id = (os.environ.get("PAY_IN_ID") or "").strip()
    only_completed = env_flag("ONLY_COMPLETED", True)
    since = timezone.now() - timedelta(days=days)

    qs = PayplatPayInSession.objects.select_related(
        "pay_in",
        "pay_in__order",
        "pay_in__order__status",
        "pay_in__order__solution__merchant__user",
    ).filter(pay_in__isnull=False, pay_in__order__isnull=False)

    if pay_in_id:
        qs = qs.filter(pay_in_id=pay_in_id)
    else:
        qs = qs.filter(updated_at__gte=since)

    print(
        f"mode={'APPLY' if apply else 'DRY_RUN'}  DAYS={days}  "
        f"since={since.isoformat()}  ONLY_COMPLETED={int(only_completed)}  "
        f"PAY_IN_ID={pay_in_id or '-'}"
    )
    print()

    planned: list[tuple] = []
    skipped: list[tuple[str, str]] = []
    scanned = 0

    for session in qs.iterator(chunk_size=200):
        scanned += 1
        pay_in = session.pay_in
        order = pay_in.order if pay_in else None
        if order is None:
            continue

        body = session.last_webhook_payload or {}
        if not isinstance(body, dict) or not body:
            skipped.append((str(pay_in.id), "empty last_webhook_payload"))
            continue

        if payplat_webhook_outcome(body) != "success":
            continue

        paid = payplat_webhook_paid_amount(body)
        if paid is None:
            skipped.append((str(pay_in.id), "no quote_amount in last webhook"))
            continue

        status = order.status.name if order.status_id else "-"
        if only_completed and status != "Completed":
            skipped.append((str(pay_in.id), f"status={status}"))
            continue

        old_amount = q2(order.amount)
        new_amount = q2(paid)
        if old_amount == new_amount:
            continue

        merchant = "-"
        try:
            merchant = order.solution.merchant.user.username
        except Exception:  # noqa: BLE001
            pass

        planned.append(
            (
                str(pay_in.id),
                session.provider_order_id or "",
                getattr(pay_in, "merchant_order_id", "") or "",
                status,
                merchant,
                old_amount,
                new_amount,
                q2(new_amount - old_amount),
                bool(order.recalculated),
                session,
                body,
            )
        )

    print(f"scanned sessions: {scanned}")
    print(f"need recalc: {len(planned)}")
    if planned:
        total_delta = q2(sum((row[7] for row in planned), Decimal("0")))
        print(f"sum delta (quote - current): {total_delta}")
        print()
        print(
            f"{'pay_in':36}  {'prov':10}  {'merchant_oid':14}  "
            f"{'status':10}  {'merchant':16}  {'old':>12}  {'quote':>12}  {'delta':>12}  recalc"
        )
        for row in planned:
            (
                pid,
                provid,
                moid,
                status,
                merchant,
                old_amount,
                new_amount,
                delta,
                was_recalc,
                *_rest,
            ) = row
            print(
                f"{pid:36}  {str(provid)[:10]:10}  {str(moid)[:14]:14}  "
                f"{status:10}  {merchant[:16]:16}  {old_amount:>12}  {new_amount:>12}  "
                f"{delta:>12}  {int(was_recalc)}"
            )

    if skipped and env_flag("SHOW_SKIPPED", False):
        print()
        print(f"skipped (sample): {len(skipped)}")
        for pid, reason in skipped[:50]:
            print(f"  {pid}: {reason}")

    if not apply:
        print()
        print("DRY_RUN — деньги не трогали. Для применения: -e APPLY=1")
        return

    print()
    print("APPLY…")
    ok = 0
    fail = 0
    for row in planned:
        pid, provid, moid, status, merchant, old_amount, new_amount, delta, was_recalc, session, body = row
        try:
            with transaction.atomic():
                # Без select_related: FOR UPDATE + outer join по status падает на Postgres.
                locked = InOrder.objects.select_for_update().get(pk=session.pay_in.order_id)
                outcome = handle_psp_success_webhook(locked, body)
                locked.refresh_from_db()
                session.pay_in.refresh_from_db()
            print(
                f"OK {pid} {old_amount} → {locked.amount} outcome={outcome} "
                f"merchant_oid={moid} provider={provid}"
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"FAIL {pid} {old_amount} → {new_amount}: {exc}")
            traceback.print_exc()

    print()
    print(f"done ok={ok} fail={fail}")


run()
