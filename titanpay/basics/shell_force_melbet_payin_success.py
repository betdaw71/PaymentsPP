"""
Melbet: Cannot process → назначить живому трейдеру → Success + callback.

Для теста local KGS (и любых Melbet pay-in без реквизита).

Inspect:
  MERCHANT_ORDER_ID=5547812021 TRADER=resdfe \\
  docker compose exec -T -e MERCHANT_ORDER_ID -e TRADER app \\
    python manage.py shell < titanpay/basics/shell_force_melbet_payin_success.py

Apply:
  MERCHANT_ORDER_ID=5547812021 TRADER=resdfe APPLY=1 \\
  docker compose exec -T -e MERCHANT_ORDER_ID -e TRADER -e APPLY app \\
    python manage.py shell < titanpay/basics/shell_force_melbet_payin_success.py
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from basics.models import PaymentDetails, Trader, TraderTeamRates
from merchant.tiered_mdr import merchant_payin_fee
from payments.dual_fx import apply_dual_fx_to_order
from payments.integrations.melbet.callbacks import try_send_melbet_payin_callback
from payments.models import PayIn, PayInStatus
from payments.psp_payin import ensure_psp_frozen_for_complete
from trade.models import InOrder, InOrderStatus, InOrderStatusChange

MOID = (os.environ.get("MERCHANT_ORDER_ID") or os.environ.get("ORDER_ID") or "").strip()
TRADER = (os.environ.get("TRADER") or "resdfe").strip() or "resdfe"
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
SEND_CB = (os.environ.get("SEND_CALLBACK") or "1").strip().lower() not in {"0", "false", "no"}


def _find_payin(moid: str) -> PayIn | None:
    return (
        PayIn.objects.select_related(
            "status",
            "currency",
            "payment_system",
            "merchant__user",
            "order__status",
            "order__solution__merchant__user",
            "order__solution__payment_system",
            "order__payment_details__group__trader__user",
        )
        .filter(merchant_order_id=moid)
        .order_by("-created_at")
        .first()
    )


def _pick_detail(trader: Trader, ps_name: str, currency_id) -> PaymentDetails | None:
    qs = (
        PaymentDetails.objects.filter(
            status=1,
            group__status=1,
            group__in_active=True,
            group__trader=trader,
            group__payment_system__name__iexact=ps_name,
        )
        .select_related("group", "group__payment_system", "group__trader__user")
        .order_by("-creation_date")
    )
    if currency_id:
        qs = qs.filter(group__currency_id=currency_id)
    for d in qs:
        has_qr = bool((d.qr_payload or "").strip())
        has_phone = bool((d.phone or "").strip())
        has_card = bool((d.card_number or "").strip())
        name = (ps_name or "").upper()
        if name == "QRKGS" and (has_qr or has_phone or has_card):
            return d
        if name == "PHONEKGS" and has_phone:
            return d
        if name in {"C2CKGS", "C2CKZT", "C2C"} and has_card:
            return d
        if has_card or has_phone or has_qr:
            return d
    return None


def _ensure_fees(order: InOrder, detail: PaymentDetails) -> None:
    trader = detail.group.trader
    ps = order.solution.payment_system
    quote = apply_dual_fx_to_order(order, trader, amount=order.amount, payment_system=ps)
    order.usd_amount = quote.merchant_usd
    order.merchant_fee = merchant_payin_fee(
        solution=order.solution, amount=order.amount, usd_amount=order.usd_amount
    )
    rate = TraderTeamRates.objects.filter(team=trader.team, payment_system=ps).first()
    if rate is None:
        raise RuntimeError(f"No TraderTeamRates team={trader.team} ps={ps.name}")
    order.trader_fee = (rate.mdr_in * quote.psp_usd / Decimal(100)).quantize(Decimal("0.01"))
    order.payment_details = detail
    order.save(
        update_fields=[
            "usd_amount",
            "merchant_fee",
            "trader_fee",
            "payment_details",
            "updated_date",
        ]
    )


def _has_open_freeze(order: InOrder) -> bool:
    from trade.models import Transaction

    freezes = Transaction.objects.filter(
        linked_in_order=order, transaction_type__name="Freeze"
    ).count()
    deposits = Transaction.objects.filter(
        linked_in_order=order, transaction_type__name="Deposit"
    ).count()
    return freezes > deposits


def inspect(pay_in: PayIn) -> None:
    order = pay_in.order
    print("=== inspect ===")
    print(f"  merchant_order_id={pay_in.merchant_order_id}")
    print(f"  pay_in={pay_in.id} status={pay_in.status.name if pay_in.status_id else None}")
    print(f"  amount={pay_in.amount} {pay_in.currency.symbol if pay_in.currency_id else '?'}")
    print(f"  payment_system={pay_in.payment_system.name if pay_in.payment_system_id else None}")
    print(f"  merchant={pay_in.merchant.user.username if pay_in.merchant_id else None}")
    if order is None:
        print("  ERROR: no InOrder")
        return
    print(f"  in_order={order.id} status={order.status.name if order.status_id else None}")
    pd = order.payment_details
    if pd:
        print(
            f"  detail={pd.id} trader={pd.group.trader.user.username} "
            f"ps={pd.group.payment_system.name}"
        )
    else:
        print("  detail=None")


def apply(pay_in: PayIn, trader: Trader) -> None:
    order = pay_in.order
    if order is None:
        raise RuntimeError("PayIn has no InOrder")

    ps = order.solution.payment_system if order.solution_id else pay_in.payment_system
    if ps is None:
        raise RuntimeError("No payment_system on order/pay_in")
    ps_name = ps.name

    with transaction.atomic():
        od = InOrder.objects.select_for_update().select_related(
            "status", "solution", "solution__payment_system", "payment_details"
        ).get(pk=order.pk)
        st = od.status.name if od.status_id else None
        allowed = {"Cannot process", "New", "Money sent by user", "Expired", "Cancelled"}
        if st == "Completed":
            print("Already Completed — skip ledger, will refresh callback only")
        elif st not in allowed:
            raise RuntimeError(f"Refuse to complete from InOrder status={st}")

        if st != "Completed":
            detail = od.payment_details
            if detail is None or detail.group.trader_id != trader.id:
                detail = _pick_detail(trader, ps_name, pay_in.currency_id)
            if detail is None:
                raise RuntimeError(
                    f"No active PaymentDetails for trader={TRADER} ps={ps_name}. "
                    "Добавьте реквизит в ЛК."
                )
            print(f"  use detail={detail.id} trader={TRADER} ps={ps_name}")

            # Cannot process / Expired / Cancelled → New + attach
            if st in {"Cannot process", "Expired", "Cancelled"} or od.payment_details_id != detail.id:
                new_st = InOrderStatus.objects.get(name="New")
                od.status = new_st
                od.payment_details = detail
                od.updated_date = timezone.now()
                od.save(update_fields=["status", "payment_details", "updated_date"])
                InOrderStatusChange.create(order=od, status=new_st)
                _ensure_fees(od, detail)
                od.refresh_from_db()
                if not _has_open_freeze(od):
                    od.freeze("Shell: force Melbet success freeze")
                    print("  + freeze")
            elif st in {"New", "Money sent by user"}:
                if od.payment_details_id != detail.id:
                    od.payment_details = detail
                    od.save(update_fields=["payment_details", "updated_date"])
                    _ensure_fees(od, detail)
                    od.refresh_from_db()
                if not _has_open_freeze(od):
                    od.freeze("Shell: force Melbet success freeze")
                    print("  + freeze")

            ensure_psp_frozen_for_complete(od)
            od.complete_after_new()
            print("  -> InOrder Completed via complete_after_new")

        pi = PayIn.objects.select_for_update().select_related("status").get(pk=pay_in.pk)
        if not pi.status or pi.status.name != "Success":
            ok = PayInStatus.objects.get(name="Success")
            pi.status = ok
            pi.updated_at = timezone.now()
            pi.save(update_fields=["status", "updated_at"])
            print("  -> PayIn Success (forced sync)")

    pay_in.refresh_from_db()
    order.refresh_from_db()
    print(
        f"DONE pay_in={pay_in.status.name} in_order={order.status.name} "
        f"trader={order.payment_details.group.trader.user.username if order.payment_details_id else None}"
    )
    if SEND_CB:
        sent = try_send_melbet_payin_callback(pay_in, status_name="Success")
        print(f"  melbet callback scheduled/sent={sent}")
        if not sent:
            print("  WARN: no Melbet session/callback_url — ping Melbet manually if needed")


def run() -> None:
    if not MOID:
        print("ERROR: set MERCHANT_ORDER_ID=...")
        return
    print(f"MERCHANT_ORDER_ID={MOID} TRADER={TRADER} APPLY={APPLY}")
    pay_in = _find_payin(MOID)
    if pay_in is None:
        from payments.models import PayOut

        po = PayOut.objects.filter(merchant_order_id=MOID).order_by("-created_at").first()
        if po is not None:
            print(
                f"FOUND PayOut id={po.id} status={po.status.name if po.status_id else None} "
                "— это ВЫВОД, не депозит. Этот скрипт только для pay-in."
            )
            return
        print("NOT FOUND PayIn/PayOut by merchant_order_id")
        return

    inspect(pay_in)
    trader = Trader.objects.select_related("user", "team", "balance_usdt").filter(
        user__username=TRADER
    ).first()
    if trader is None:
        print(f"ERROR: trader {TRADER!r} not found")
        return
    detail_preview = None
    ps = pay_in.payment_system
    if ps is not None:
        detail_preview = _pick_detail(trader, ps.name, pay_in.currency_id)
    print(
        f"  target trader={TRADER} detail_ready="
        f"{detail_preview.id if detail_preview else None}"
    )
    if not APPLY:
        print("DRY-RUN — set APPLY=1 to assign + Success + Melbet callback")
        return
    apply(pay_in, trader)


run()
