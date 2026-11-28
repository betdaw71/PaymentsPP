"""
PayPlat payout: осмотр IPN/колбеков и принудительный Success, если провайдер оплатил.

Поздний PAID после expire/Cannot process раньше сохранялся в last_webhook_payload
и отдавал HTTP 200, но OutOrder.complete() шёл только из New, а PayOut.success()
пропускал Failed/Declined. Если IPN уже пришёл — APPLY применит его без повторного
колбека от PayPlat. Если IPN нет, а провайдер письменно подтвердил оплату —
APPLY_FORCE=1.

Осмотр (ничего не пишет):
  docker compose exec -T \\
    -e IDS=064936ab-f1ce-4a17-8c79-15048c69dfdc,20a882a1-8182-4bf7-a9bf-9af3c44bb8d1 \\
    app python manage.py shell < titanpay/basics/shell_payplat_payout_paid_apply.py

Dry-run применения:
  docker compose exec -T -e ACTION=apply -e DRY_RUN=1 \\
    -e IDS=064936ab-f1ce-4a17-8c79-15048c69dfdc,20a882a1-8182-4bf7-a9bf-9af3c44bb8d1 \\
    app python manage.py shell < titanpay/basics/shell_payplat_payout_paid_apply.py

Боевое применение (если last_webhook PAID/SUCCESS):
  docker compose exec -T -e ACTION=apply \\
    -e IDS=064936ab-f1ce-4a17-8c79-15048c69dfdc,20a882a1-8182-4bf7-a9bf-9af3c44bb8d1 \\
    app python manage.py shell < titanpay/basics/shell_payplat_payout_paid_apply.py

Провайдер подтвердил оплату, IPN нет:
  docker compose exec -T -e ACTION=apply -e APPLY_FORCE=1 \\
    -e IDS=064936ab-f1ce-4a17-8c79-15048c69dfdc,20a882a1-8182-4bf7-a9bf-9af3c44bb8d1 \\
    app python manage.py shell < titanpay/basics/shell_payplat_payout_paid_apply.py
"""
from __future__ import annotations

import json
import os

from django.db.models import Q

from payments.models import PayInTraceLog, PayOut, PayplatPayOutSession
from payments.payplat_client import (
    apply_payplat_payout_paid,
    out_order_has_unreversed_freeze,
    payplat_webhook_outcome,
)
from trade.models import OutOrder, Transaction

DEFAULT_IDS = (
    "064936ab-f1ce-4a17-8c79-15048c69dfdc",
    "20a882a1-8182-4bf7-a9bf-9af3c44bb8d1",
)
PAID_STATUSES = frozenset({"paid", "success"})


def _ids() -> list[str]:
    raw = (os.environ.get("IDS") or os.environ.get("PAY_OUT_ID") or "").strip()
    if raw:
        return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
    return list(DEFAULT_IDS)


def _flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _payload(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _preview(raw, limit: int = 900) -> str:
    text = json.dumps(raw, ensure_ascii=False, default=str) if not isinstance(raw, str) else raw
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def resolve_pay_out(lookup: str) -> PayOut | None:
    po = (
        PayOut.objects.select_related(
            "status",
            "merchant__user",
            "currency",
            "payment_system",
            "order__status",
            "order__solution__merchant__user",
            "order__solution__payment_system",
            "order__payment_details__group__trader__user",
        )
        .filter(id=lookup)
        .first()
    )
    if po is not None:
        return po
    return (
        PayOut.objects.select_related(
            "status",
            "merchant__user",
            "currency",
            "payment_system",
            "order__status",
            "order__solution__merchant__user",
            "order__solution__payment_system",
            "order__payment_details__group__trader__user",
        )
        .filter(merchant_order_id=lookup)
        .order_by("-created_at")
        .first()
    )


def _webhook_looks_paid(session: PayplatPayOutSession | None) -> bool:
    if session is None:
        return False
    last = _payload(session.last_webhook_payload)
    if payplat_webhook_outcome(last, payout=True) == "success":
        return True
    notified = (session.last_notified_status or "").strip().lower()
    if notified in PAID_STATUSES:
        return True
    created = _payload(session.create_response)
    return (created.get("status") or "").strip().lower() in PAID_STATUSES


def _print_traces(pay_out: PayOut) -> None:
    q = Q(merchant_order_id=pay_out.merchant_order_id) | Q(body__shop_internal_id=str(pay_out.id))
    q |= Q(body__pay_out_id=str(pay_out.id))
    logs = list(PayInTraceLog.objects.filter(q).order_by("created_at"))
    print(f"  traces={len(logs)}")
    if not logs:
        print("  (payout IPN historically not traced; смотрите PayplatPayOutSession.last_webhook)")
    for t in logs:
        print(
            f"    {t.created_at:%Y-%m-%d %H:%M:%S} {t.direction:22} "
            f"http={t.status_code or '-'} {t.note}"
        )
        print(f"      {_preview(t.body)}")


def _print_ledger(order: OutOrder | None) -> None:
    if order is None:
        return
    txs = list(
        Transaction.objects.filter(linked_out_order=order)
        .select_related("transaction_type")
        .order_by("creation_date")
    )
    print(f"  ledger txs={len(txs)} freeze_active={out_order_has_unreversed_freeze(order)}")
    for tx in txs:
        tname = tx.transaction_type.name if tx.transaction_type else None
        print(f"    {tx.creation_date:%Y-%m-%d %H:%M:%S} {tname} {tx.value} {tx.comment}")


def inspect_one(lookup: str) -> PayOut | None:
    print("=" * 72)
    print(f"lookup={lookup}")
    po = resolve_pay_out(lookup)
    if po is None:
        print("  NOT FOUND as PayOut")
        return None
    od = po.order
    trader = None
    if od and od.payment_details_id:
        trader = od.payment_details.group.trader.user.username
    print("  KIND=PayOut")
    print(f"  pay_out={po.id} status={po.status.name if po.status else None}")
    print(f"  merchant={po.merchant.user.username if po.merchant_id else None}")
    print(f"  moid={po.merchant_order_id} amount={po.amount} {po.currency.symbol if po.currency_id else ''}")
    print(f"  ps={po.payment_system.name if po.payment_system_id else None}")
    print(f"  callback_url={po.callback_url}")
    if od:
        print(
            f"  out_order={od.id} status={od.status.name if od.status else None} "
            f"trader={trader} details={od.payment_details_id}"
        )
        prev = list(od.previous_orders.select_related("status").all()) if hasattr(od, "previous_orders") else []
        if prev:
            print("  previous_orders:")
            for item in prev:
                print(
                    f"    {item.id} status={item.status.name if item.status else None} "
                    f"details={item.payment_details_id}"
                )
        related = (
            OutOrder.objects.filter(merchant_order_id=od.merchant_order_id, solution_id=od.solution_id)
            .exclude(pk=od.pk)
            .select_related("status")
            .order_by("-creation_date")[:8]
        )
        for item in related:
            print(
                f"  related_out={item.id} status={item.status.name if item.status else None} "
                f"details={item.payment_details_id}"
            )

    session = (
        PayplatPayOutSession.objects.filter(pay_out=po)
        .select_related("pay_out")
        .first()
    )
    if session is None:
        print("  PayplatPayOutSession: MISSING — IPN не к чему привязать")
    else:
        last = _payload(session.last_webhook_payload)
        created = _payload(session.create_response)
        outcome = payplat_webhook_outcome(last, payout=True) if last else None
        print(
            f"  session external_id={session.external_id} provider_payout_id={session.provider_payout_id} "
            f"last_notified={session.last_notified_status} outcome={outcome} paid={_webhook_looks_paid(session)}"
        )
        print(f"    create_response={_preview(created)}")
        print(f"    last_webhook={_preview(last) if last else '(empty — IPN не приняли или не приходил)'}")

    _print_ledger(od)
    _print_traces(po)
    cbs = list(
        PayInTraceLog.objects.filter(
            Q(merchant_order_id=po.merchant_order_id) | Q(body__pay_out_id=str(po.id)),
            direction="merchant_callback",
        ).order_by("created_at")
    )
    if not cbs:
        print("  merchant_callback: нет в PayInTraceLog (до фикса payout callback не писался в trace)")
    return po


def apply_one(pay_out: PayOut, *, dry_run: bool, force: bool) -> None:
    session = PayplatPayOutSession.objects.filter(pay_out=pay_out).select_related("pay_out", "pay_out__order").first()
    if session is None:
        raise ValueError(f"{pay_out.id}: no PayplatPayOutSession")
    paid = _webhook_looks_paid(session)
    if not paid and not force:
        raise ValueError(
            f"{pay_out.id}: last_webhook not PAID; set APPLY_FORCE=1 only if provider confirmed payment"
        )
    print(
        f"  apply pay_out={pay_out.id} paid={paid} force={force} dry_run={dry_run} "
        f"po={pay_out.status.name if pay_out.status else None} "
        f"oo={pay_out.order.status.name if pay_out.order and pay_out.order.status else None}"
    )
    if dry_run:
        print("  DRY_RUN skip apply_payplat_payout_paid")
        return
    result = apply_payplat_payout_paid(session)
    print(f"  result={json.dumps(result, ensure_ascii=False, default=str)}")
    if not result.get("ok"):
        raise ValueError(f"{pay_out.id}: apply failed {result}")
    pay_out.refresh_from_db()
    if pay_out.order_id:
        pay_out.order.refresh_from_db()
    print(
        f"  after pay_out={pay_out.status.name if pay_out.status else None} "
        f"out_order={pay_out.order.status.name if pay_out.order and pay_out.order.status else None}"
    )


ACTION = (os.environ.get("ACTION") or "inspect").strip().lower()
DRY_RUN = _flag("DRY_RUN")
FORCE = _flag("APPLY_FORCE")

lookups = _ids()
print(f"ACTION={ACTION} DRY_RUN={DRY_RUN} APPLY_FORCE={FORCE} ids={lookups}")

errors = []
for lookup in lookups:
    po = inspect_one(lookup)
    if po is None:
        errors.append(f"{lookup}: not found")
        continue
    if ACTION != "apply":
        continue
    try:
        apply_one(po, dry_run=DRY_RUN, force=FORCE)
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
        print(f"  ERROR {exc}")

if errors:
    print("ERRORS:")
    for item in errors:
        print(f"  {item}")
    raise SystemExit(1)
print("OK")
