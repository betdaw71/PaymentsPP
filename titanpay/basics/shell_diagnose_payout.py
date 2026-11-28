"""
Диагностика выплатной заявки: Cannot process при том, что ушла на PSP.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_diagnose_payout.py

Или:
  docker compose exec -T -e PAYOUT_ID=b8f2c509-6ba1-48ce-be70-b779037cc35f app \\
    python manage.py shell < titanpay/basics/shell_diagnose_payout.py
"""
from __future__ import annotations

import json
import os
from zoneinfo import ZoneInfo

from django.db.models import Q

from payments.models import (
    AstrumPayOutSession,
    PayInTraceLog,
    PayOut,
    PayplatPayOutSession,
    PlaymentsPayOutSession,
)
from trade.models import OutOrder, Transaction

MSK = ZoneInfo("Europe/Moscow")
TARGET = (
    os.environ.get("PAYOUT_ID") or "1a852078-e205-4883-b58e-3f0a85b1999f"
).strip()


def when(dt):
    if not dt:
        return "-"
    if getattr(dt, "tzinfo", None):
        return dt.astimezone(MSK).strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


def dump(obj, n=4000):
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except TypeError:
        text = str(obj)
    if len(text) > n:
        return text[:n] + "…"
    return text


def find_payout(raw: str):
    po = PayOut.objects.filter(id=raw).select_related(
        "status", "currency", "payment_system", "merchant__user", "order", "order__status",
        "order__payment_details__group__trader__user", "order__solution__payment_system",
        "client",
    ).first()
    if po:
        return po
    od = OutOrder.objects.filter(id=raw).select_related("status").first()
    if od:
        return PayOut.objects.filter(order=od).select_related(
            "status", "currency", "payment_system", "merchant__user", "order", "order__status",
            "order__payment_details__group__trader__user", "order__solution__payment_system",
            "client",
        ).first()
    return (
        PayOut.objects.filter(merchant_order_id=raw)
        .select_related(
            "status", "currency", "payment_system", "merchant__user", "order", "order__status",
            "order__payment_details__group__trader__user", "order__solution__payment_system",
            "client",
        )
        .order_by("-created_at")
        .first()
    )


def print_session(label, sess):
    if sess is None:
        print(f"  {label}: нет")
        return
    print(f"  {label}: id={sess.id}  external_id={getattr(sess, 'external_id', None)}")
    for attr in ("provider_payout_id", "provider_application_id", "provider_withdrawal_id"):
        val = getattr(sess, attr, None)
        if val:
            print(f"    {attr}={val}")
    print(f"    last_state={getattr(sess, 'last_notified_status', None) or getattr(sess, 'last_notified_state', None)}")
    print(f"    created={when(sess.created_at)}  updated={when(sess.updated_at)}")
    print(f"    create_response={dump(getattr(sess, 'create_response', None))}")
    print(f"    last_webhook={dump(getattr(sess, 'last_webhook_payload', None))}")


pay_out = find_payout(TARGET)
print(f"diagnose payout {TARGET}\n")
if pay_out is None:
    print("NOT FOUND as PayOut.id / OutOrder.id / merchant_order_id")
else:
    order = pay_out.order
    merch = pay_out.merchant.user.username if pay_out.merchant_id else "-"
    print(f"PayOut={pay_out.id}  status={pay_out.status.name if pay_out.status else '-'}")
    print(f"  merchant={merch}  moid={pay_out.merchant_order_id}")
    print(
        f"  amount={pay_out.amount} {pay_out.currency.symbol if pay_out.currency else ''}  "
        f"ps={pay_out.payment_system.name if pay_out.payment_system else '-'}"
    )
    print(f"  created={when(pay_out.created_at)}  updated={when(pay_out.updated_at)}")
    print(f"  details={dump(pay_out.details, 800)}")
    if order is None:
        print("  OutOrder: нет")
    else:
        pd = order.payment_details
        trader = "-"
        if pd and pd.group_id and pd.group.trader_id:
            trader = pd.group.trader.user.username
        print(
            f"  OutOrder={order.id}  status={order.status.name if order.status else '-'}  "
            f"amount={order.amount}  usd={order.usd_amount}"
        )
        print(
            f"  created={when(order.creation_date)}  updated={when(order.updated_date)}  "
            f"completed={when(order.completion_date)}"
        )
        print(f"  payment_details={pd.id if pd else None}  trader={trader}")
        print(f"  destination={dump(order.destination_details, 800)}")
        if pd is None:
            print("  HINT: payment_details=None → роутинг не выбрал трейдера (заявки у PayPlat нет)")
        elif order.status and order.status.name == "Cannot process":
            print(
                "  HINT: трейдер выбран, статус сразу Cannot process → "
                "create в PayPlat не принят (HTTP/reject) ИЛИ нет card_number в details. "
                "Сессия PayplatPayOutSession создаётся ДО ответа PayPlat — в ЛК видно «ушло на payplat», "
                "хотя у них заявки может не быть."
            )

    from payments.payplat_client import (
        _card_from_payout,
        _payout_amount_for_payplat,
        payplat_payout_create_rejected,
    )

    card = _card_from_payout(pay_out)
    print("\nWhat we would send to PayPlat:")
    print(f"  shop_internal_id={pay_out.id}  (этим ID спрашивать PayPlat, не merchant_order_id)")
    print(f"  amount_for_payplat={_payout_amount_for_payplat(pay_out)}")
    print(f"  card_digits={len(card) if card else 0}  last4={card[-4:] if card else '-'}")
    if not card:
        print("  HINT: card_number/requisite/card нет в details → create даже не уходит, статус сразу Cannot process")

    print("\nPSP sessions:")
    sess = PayplatPayOutSession.objects.filter(pay_out=pay_out).first()
    print_session("payplat", sess)
    if sess is not None:
        cr = sess.create_response if isinstance(sess.create_response, dict) else {}
        print(f"    create_rejected={payplat_payout_create_rejected(cr)}")
        print(f"    provider_payout_id={sess.provider_payout_id or '-'}")
        if not sess.provider_payout_id:
            print("    HINT: нет provider_payout_id → PayPlat заявку не завели (или ответили без id)")
    print_session("astrum", AstrumPayOutSession.objects.filter(pay_out=pay_out).first())
    print_session("playments", PlaymentsPayOutSession.objects.filter(pay_out=pay_out).first())

    print("\nTransactions:")
    txs = (
        Transaction.objects.filter(linked_out_order=order)
        .select_related("transaction_type")
        .order_by("creation_date")
        if order
        else []
    )
    if not txs:
        print("  нет")
    for tx in txs:
        print(
            f"  {when(tx.creation_date)}  {tx.transaction_type.name if tx.transaction_type else '-'}  "
            f"{tx.value}  {tx.comment}"
        )

    print("\nTrace:")
    moids = {pay_out.merchant_order_id or "", str(pay_out.id)}
    traces = PayInTraceLog.objects.filter(
        Q(merchant_order_id__in=[m for m in moids if m])
        | Q(note__icontains=str(pay_out.id))
        | Q(note__icontains=TARGET)
    ).order_by("created_at")[:80]
    if not traces:
        print("  нет")
    for t in traces:
        print(f"  {when(t.created_at)}  {t.direction:28}  http={t.status_code}  {t.note}")
        print(f"    url={t.url}")
        print(f"    body={dump(t.body, 1500)}")
