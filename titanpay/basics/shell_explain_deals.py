"""Разбор сделок по UUID (PayIn / InOrder / merchant_order_id) — статусы, трейдер, банк, traces.

  docker compose exec -T \\
    -e DEAL_IDS='4075cfd9-...,41e2d937-...' \\
    app python manage.py shell < titanpay/basics/shell_explain_deals.py
"""
from __future__ import annotations

import os
from decimal import Decimal

from payments.models import PayIn, PayInTraceLog
from payments.psp_payin import requisite_for_payin
from trade.models import InOrder

DEFAULT_IDS = (
    "4075cfd9-1673-4f78-aedb-3b8cb42154c8",
    "41e2d937-7468-429f-974c-111dfc2a1e21",
    "088ae9a3-9751-4e22-a723-62a4a45d25f9",
    "3c8e0d4c-02d4-4c7c-8aa3-5ca120c97e72",
)

SESSION_MODELS = (
    "PayplatPayInSession",
    "GipayPayInSession",
    "VisionxPayInSession",
    "PatriotpayPayInSession",
    "LayeronePayInSession",
    "PlutusPayInSession",
    "ProchubPayInSession",
    "NexusPayInSession",
    "AstrumPayInSession",
    "BitzonePayInSession",
    "ProtocolPayInSession",
)


def _ids() -> list[str]:
    raw = (os.environ.get("DEAL_IDS") or "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    return list(DEFAULT_IDS)


_PAYIN_RELATED = (
    "status",
    "currency",
    "payment_system",
    "merchant__user",
    "order__status",
    "order__solution__merchant__user",
    "order__solution__payment_system",
    "order__payment_details__group__trader__user",
    "order__payment_details__group__payment_system",
)


def _find_payin(deal_id: str):
    pay = PayIn.objects.select_related(*_PAYIN_RELATED).filter(id=deal_id).first()
    if pay:
        return pay, pay.order
    pay = (
        PayIn.objects.select_related(*_PAYIN_RELATED)
        .filter(merchant_order_id=deal_id)
        .order_by("-created_at")
        .first()
    )
    if pay:
        return pay, pay.order
    order = (
        InOrder.objects.select_related(
            "status",
            "solution__merchant__user",
            "solution__payment_system",
            "payment_details__group__trader__user",
            "payment_details__group__payment_system",
        )
        .filter(id=deal_id)
        .first()
    )
    if order:
        return order.pay_in.first(), order
    return None, None


def _psp_sessions(pay_in):
    out = []
    if pay_in is None:
        return out
    for name in SESSION_MODELS:
        model = getattr(__import__("payments.models", fromlist=[name]), name, None)
        if model is None:
            continue
        for s in model.objects.filter(pay_in=pay_in).order_by("-created_at")[:3]:
            last = (
                getattr(s, "last_notified_state", None)
                or getattr(s, "last_notified_status", None)
                or getattr(s, "last_notified_sub_status", None)
                or "-"
            )
            out.append(
                {
                    "model": name,
                    "id": getattr(s, "id", None),
                    "last": last,
                    "has_webhook": bool(getattr(s, "last_webhook_payload", None)),
                    "provider_invoice": getattr(s, "provider_invoice_id", None)
                    or getattr(s, "invoice_id", None)
                    or getattr(s, "external_id", None),
                }
            )
    return out


def _reason_guess(pay_in, order) -> str:
    pay_st = pay_in.status.name if pay_in and pay_in.status_id else None
    ord_st = order.status.name if order and order.status_id else None
    comment = (getattr(order, "arbitrage_comment", None) or "").strip() if order else ""
    has_detail = bool(order and order.payment_details_id)

    if ord_st == "Cannot process" or (pay_st == "Declined" and not has_detail):
        return "Нет реквизита / Cannot process (роутинг не выдал карту)"
    if ord_st in {"Expired", "Cancelled", "Cancelled by trader", "Cancelled by support"} or pay_st in {
        "Failed",
        "Expired",
    }:
        if comment:
            return f"Истекла/отмена: {ord_st or pay_st}; {comment}"
        return f"Клиент не оплатил / таймаут ({ord_st or pay_st})"
    if pay_st == "Declined":
        return f"Declined (order={ord_st or '-'})" + (f"; {comment}" if comment else "")
    if pay_st == "Success":
        return "Успех — отказ не подтверждается"
    return f"Статус payin={pay_st} order={ord_st}"


def explain(deal_id: str) -> None:
    print("=" * 78)
    print(f"ID: {deal_id}")
    pay_in, order = _find_payin(deal_id)

    if pay_in is None and order is None:
        print("  NOT FOUND")
        return

    if pay_in is None and order is not None:
        print(f"  InOrder only id={order.id}")
    merchant = None
    if pay_in and pay_in.merchant_id:
        merchant = pay_in.merchant
    elif order and order.solution_id:
        merchant = order.solution.merchant

    ps = pay_in.payment_system if pay_in else (order.solution.payment_system if order else None)
    trader = None
    group_ps = None
    if order and order.payment_details_id:
        try:
            trader = order.payment_details.group.trader
            group_ps = order.payment_details.group.payment_system
        except Exception:  # noqa: BLE001
            pass

    bank = None
    try:
        req = requisite_for_payin(pay_in) if pay_in else None
        if req:
            bank = req.get("bank") or req.get("bankName")
    except Exception:  # noqa: BLE001
        bank = None
    if not bank and group_ps:
        bank = group_ps.name

    print(f"  merchant:     {merchant.user.username if merchant and merchant.user_id else '-'}")
    print(f"  merchant_oid: {getattr(pay_in, 'merchant_order_id', None) or getattr(order, 'merchant_order_id', None)}")
    print(f"  pay_in:       {pay_in.id if pay_in else '-'}  status={pay_in.status.name if pay_in and pay_in.status_id else '-'}")
    print(f"  order:        {order.id if order else '-'}  status={order.status.name if order and order.status_id else '-'}")
    print(f"  amount:       {getattr(pay_in, 'amount', None) or getattr(order, 'amount', None)} {getattr(getattr(pay_in, 'currency', None), 'symbol', '')}")
    print(f"  usd:          {getattr(order, 'usd_amount', None)}  merchant_rate={getattr(order, 'merchant_rate', None)} psp_rate={getattr(order, 'psp_rate', None)}")
    print(f"  PS:           {ps.name if ps else '-'}")
    print(f"  trader:       {trader.user.username if trader and trader.user_id else '(no_req)'}")
    print(f"  bank/group:   {bank or '-'} / {group_ps.name if group_ps else '-'}")
    if order:
        print(f"  arb_comment:  {order.arbitrage_comment!r}")
        print(f"  created:      {order.creation_date}")
        print(f"  updated:      {order.updated_date}")
    elif pay_in:
        print(f"  created:      {pay_in.created_at}")

    print(f"  REASON:       {_reason_guess(pay_in, order)}")

    for s in _psp_sessions(pay_in):
        print(
            f"  PSP session:  {s['model']} last={s['last']} "
            f"webhook={int(s['has_webhook'])} inv={s['provider_invoice']}"
        )

    if pay_in is not None:
        traces = list(
            PayInTraceLog.objects.filter(pay_in=pay_in).order_by("-created_at")[:12]
        )
        if traces:
            print("  traces (last 12):")
            for t in traces:
                print(
                    f"    {t.created_at} dir={t.direction} "
                    f"code={t.status_code} note={(t.note or '')[:120]}"
                )


print(f"Explain deals n={len(_ids())}")
for deal_id in _ids():
    explain(deal_id)
print("DONE")
