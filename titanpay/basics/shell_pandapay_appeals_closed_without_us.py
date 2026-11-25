"""
PandaPay: апелляции, которые у нас ещё «открыты», а сделка уже закрыта
без ответа наших кнопок провайдера (SLA / колбек / закрытие на стороне мерчанта).

Также печатает все открытые pandapay-апелляции за окно.

Запуск (из ~/project на проде):

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_pandapay_appeals_closed_without_us.py

Интерактивно:

  >>> exec(open("basics/shell_pandapay_appeals_closed_without_us.py").read())
  >>> run(hours=168)
  >>> run(hours=96, apply_sync=True)  # пометить appeal approved/rejected по статусу ордера

Переменные окружения:
  HOURS=168
  MERCHANT=pandapay
  APPLY=1              — синхронизировать open+terminal appeal с ордером
  FINALIZE_REJECT=1    — закрыть awaiting_reject_reason отказом без причины → мерчу
"""
from __future__ import annotations

import os
import uuid
from datetime import timedelta

from django.utils import timezone

from appeals.models import PayInAppeal, PayInAppealStatus
from appeals.notify import resolve_pending_appeals_for_order
from appeals.provider_actions import reject_appeal

MERCHANT = (os.environ.get("MERCHANT") or "pandapay").strip()
HOURS = int(os.environ.get("HOURS") or "168")
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes", "on"}
FINALIZE_REJECT = (os.environ.get("FINALIZE_REJECT") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

OPEN_STATUSES = (
    PayInAppealStatus.CREATED,
    PayInAppealStatus.SENT_TO_PROVIDER,
    PayInAppealStatus.AWAITING_REJECT_REASON,
)

# Сделка уже «закрыта» — ждать ответа провайдера бессмысленно.
TERMINAL_ORDER = {
    "Completed",
    "Expired",
    "Cancelled",
    "Cancelled by support",
    "Cancelled by trader",
}
TERMINAL_PAYIN = {"Success", "Failed", "Declined", "Expired"}


def _short(value, n: int = 64) -> str:
    text = (str(value) if value is not None else "").replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _row(appeal: PayInAppeal) -> dict:
    pay_in = appeal.pay_in
    order = appeal.in_order or getattr(pay_in, "order", None)
    order_st = getattr(getattr(order, "status", None), "name", None) or "—"
    pay_st = getattr(getattr(pay_in, "status", None), "name", None) or "—"
    age_h = (timezone.now() - appeal.created_at).total_seconds() / 3600.0
    closed_without_us = order_st in TERMINAL_ORDER or pay_st in TERMINAL_PAYIN
    suggested = None
    if closed_without_us:
        if order_st == "Completed" or pay_st == "Success":
            suggested = "approved"
        else:
            suggested = "rejected"
    return {
        "appeal_id": str(appeal.id),
        "created_at": appeal.created_at,
        "age_h": age_h,
        "appeal_status": appeal.status,
        "psp": appeal.psp_provider or "—",
        "ext": appeal.provider_external_id or "",
        "moid": pay_in.merchant_order_id if pay_in else "",
        "pay_in": str(pay_in.id) if pay_in else "",
        "pay_status": pay_st,
        "in_order": str(order.id) if order else "",
        "order_status": order_st,
        "closed_without_us": closed_without_us,
        "suggested": suggested,
        "err": appeal.error_message or "",
        "order": order,
    }


def run(
    hours: int = HOURS,
    merchant: str = MERCHANT,
    apply_sync: bool = APPLY,
    finalize_reject: bool = FINALIZE_REJECT,
) -> None:
    since = timezone.now() - timedelta(hours=hours)
    qs = (
        PayInAppeal.objects.filter(
            created_at__gte=since,
            pay_in__merchant__user__username=merchant,
        )
        .select_related(
            "pay_in__status",
            "pay_in__merchant__user",
            "in_order__status",
            "pay_in__order__status",
        )
        .order_by("created_at")
    )
    rows = [_row(a) for a in qs]
    open_rows = [r for r in rows if r["appeal_status"] in OPEN_STATUSES]
    closed_without = [r for r in open_rows if r["closed_without_us"]]
    still_waiting = [r for r in open_rows if not r["closed_without_us"]]

    print("=" * 72)
    print(f"PandaPay appeals  merchant={merchant}  window={hours}h  since={since.isoformat()}")
    print("=" * 72)
    print(f"всего апелляций за окно: {len(rows)}")
    print(f"сейчас открыты у нас:    {len(open_rows)}")
    print(f"  └ закрыты без нас:     {len(closed_without)}  ← список ниже")
    print(f"  └ ещё ждут ответа:     {len(still_waiting)}")

    print()
    print("=" * 72)
    print("ЗАКРЫТЫ БЕЗ НАШЕГО ОТВЕТА (appeal open, order/payin terminal)")
    print("=" * 72)
    if not closed_without:
        print("(пусто)")
    else:
        print(
            f"{'created':>20}  {'age_h':>6}  {'appeal':<22}  {'psp':<10}  "
            f"{'order_st':<18}  {'pay_st':<12}  suggest  moid"
        )
        for r in closed_without:
            print(
                f"{r['created_at'].strftime('%Y-%m-%d %H:%M'):>20}  "
                f"{r['age_h']:6.1f}  {r['appeal_status']:<22}  {r['psp']:<10}  "
                f"{r['order_status']:<18}  {r['pay_status']:<12}  "
                f"{(r['suggested'] or '—'):<7}  {_short(r['moid'], 48)}"
            )
            print(
                f"    appeal={r['appeal_id']}  pay_in={r['pay_in']}  "
                f"in_order={r['in_order']}  ext={_short(r['ext'], 40)}"
            )

    print()
    print("=" * 72)
    print("ЕЩЁ ЖДУТ (Arbitrage / In Progress и т.п.)")
    print("=" * 72)
    if not still_waiting:
        print("(пусто)")
    else:
        for r in still_waiting:
            print(
                f"  {r['created_at']} [{r['appeal_status']}] psp={r['psp']} "
                f"order={r['order_status']} pay={r['pay_status']} "
                f"moid={_short(r['moid'], 48)} age={r['age_h']:.1f}h"
            )

    print()
    print("=" * 72)
    print("КОПИПАСТА moid (closed without us)")
    print("=" * 72)
    moids = [r["moid"] for r in closed_without if r["moid"]]
    if not moids:
        print("(пусто)")
    else:
        for moid in moids:
            print(moid)

    awaiting = [r for r in open_rows if r["appeal_status"] == PayInAppealStatus.AWAITING_REJECT_REASON]
    print()
    print("=" * 72)
    print(f"AWAITING_REJECT_REASON (застряли на отказе без причины): {len(awaiting)}")
    print("=" * 72)
    if not awaiting:
        print("(пусто)")
    else:
        for r in awaiting:
            print(
                f"  {r['created_at']} psp={r['psp']} order={r['order_status']} "
                f"moid={_short(r['moid'], 48)} appeal={r['appeal_id']}"
            )

    if finalize_reject and awaiting:
        print()
        print("=" * 72)
        print(f"FINALIZE_REJECT: reject without reason × {len(awaiting)}")
        print("=" * 72)
        for r in awaiting:
            result = reject_appeal(uuid.UUID(r["appeal_id"]), reason="")
            print(f"  {r['moid']}: ok={result.ok} {result.message}")

    if apply_sync and closed_without:
        print()
        print("=" * 72)
        print(f"APPLY: sync {len(closed_without)} appeal(s) → merchant notify")
        print("=" * 72)
        for r in closed_without:
            order = r["order"]
            approved = r["suggested"] == "approved"
            if order is None:
                print(f"  skip {r['moid']}: no order")
                continue
            try:
                resolve_pending_appeals_for_order(order, approved=approved)
                print(f"  ok {r['moid']} → {'approved' if approved else 'rejected'}")
            except Exception as exc:
                print(f"  FAIL {r['moid']}: {exc}")

    print("\nГотово.")


run()
