"""
Курс и суммы по сделкам (PayIn/PayOut UUID) — для ответа мерчанту.

Пример:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_deal_rate_info.py

Несколько ID через env:
  docker compose exec -T \\
    -e DEAL_IDS='11ad67f6-8715-4e9c-bae9-f57371f3f164,1fbc2246-8a7b-46b8-9b09-6fb63aa6305c' \\
    app python manage.py shell < titanpay/basics/shell_deal_rate_info.py
"""
from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP

from merchant.kzt_settlement import in_order_credit_kzt, uses_melbet_kzt_settlement
from payments.models import PayIn, PayOut
from trade.models import InOrder, OutOrder

DEFAULT_IDS = (
    "11ad67f6-8715-4e9c-bae9-f57371f3f164",
    "1fbc2246-8a7b-46b8-9b09-6fb63aa6305c",
)


def _q(value: Decimal, places: int = 2) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.1") ** places, rounding=ROUND_HALF_UP)


def _deal_rate(fiat: Decimal, usdt: Decimal) -> Decimal | None:
    if not usdt or usdt <= 0:
        return None
    return _q(fiat / usdt, 4)


def _print_order_block(*, title: str, order, pay, direction: str) -> None:
    ps = pay.payment_system if pay else (order.solution.payment_system if order else None)
    currency = pay.currency if pay else (ps.currency if ps else None)
    merchant = pay.merchant if pay else (order.solution.merchant if order else None)

    fiat = Decimal(str(pay.amount if pay else order.amount))
    usdt = Decimal(str(order.usd_amount)) if order and order.usd_amount else Decimal("0")
    ps_rate_now = Decimal(str(ps.get_rate())) if ps else Decimal("0")
    deal_rate = _deal_rate(fiat, usdt)
    mdr = order.solution.mdr_in if direction == "in" else order.solution.mdr_out
    merchant_fee = Decimal(str(order.merchant_fee)) if order else Decimal("0")

    print(f"=== {title} ===")
    print(f"type:              {direction.upper()} ({type(pay).__name__})")
    print(f"merchant:          {merchant.user.username if merchant and merchant.user else None}")
    print(f"merchant_order_id: {pay.merchant_order_id if pay else order.merchant_order_id}")
    print(f"status:            {pay.status.name if pay and pay.status else None}")
    if order and order.status:
        print(f"order_status:      {order.status.name}")
    print(f"payment_system:    {ps.name if ps else None}")
    print(f"currency:          {currency.symbol if currency else None}")
    print(f"fiat_amount:       {fiat}")
    print(f"usdt_amount:       {usdt}")
    if deal_rate is not None:
        print(f"rate_deal:         {deal_rate} {currency.symbol if currency else ''}/USDT")
    if ps_rate_now:
        print(f"rate_ps_now:       {ps_rate_now} {currency.symbol if currency else ''}/USDT (текущий в PS)")
    print(f"mdr:               {mdr}%")
    if order and uses_melbet_kzt_settlement(order.solution.merchant, ps):
        credit = in_order_credit_kzt(order) if direction == "in" else None
        print(f"settlement:        melbet KZT (комиссия в KZT)")
        print(f"commission:        {merchant_fee} {currency.symbol if currency else ''}")
        if credit is not None:
            print(f"merchant_credit:   {credit} {currency.symbol if currency else ''}")
    else:
        fee_fiat = (merchant_fee * ps_rate_now).quantize(Decimal("0.01")) if ps_rate_now else Decimal("0")
        credit_usdt = usdt - merchant_fee if direction == "in" else usdt + merchant_fee
        print(f"commission:        {merchant_fee} USDT (~{fee_fiat} {currency.symbol if currency else ''})")
        print(f"merchant_credit:   {credit_usdt} USDT")
    if order:
        print(f"recalculated:      {order.recalculated}")
        if order.recalculated and order.recalculated_amount:
            print(f"recalc_amount:     {order.recalculated_amount}")
    print(f"created_at:        {pay.created_at if pay else order.creation_date}")
    print(f"updated_at:        {pay.updated_at if pay else order.updated_date}")
    print()


def _lookup(deal_id: str) -> None:
    deal_id = deal_id.strip()
    if not deal_id:
        return

    pay_in = PayIn.objects.select_related(
        "status",
        "currency",
        "payment_system",
        "merchant__user",
        "order__status",
        "order__solution__merchant__user",
        "order__solution__payment_system__currency",
    ).filter(id=deal_id).first()
    if pay_in:
        _print_order_block(title=str(pay_in.id), order=pay_in.order, pay=pay_in, direction="in")
        return

    pay_out = PayOut.objects.select_related(
        "status",
        "currency",
        "payment_system",
        "merchant__user",
        "order__status",
        "order__solution__merchant__user",
        "order__solution__payment_system__currency",
    ).filter(id=deal_id).first()
    if pay_out:
        _print_order_block(title=str(pay_out.id), order=pay_out.order, pay=pay_out, direction="out")
        return

    in_order = InOrder.objects.select_related(
        "status",
        "solution__merchant__user",
        "solution__payment_system__currency",
        "pay_in__status",
    ).filter(id=deal_id).first()
    if in_order:
        pay = in_order.pay_in.first()
        _print_order_block(title=str(in_order.id), order=in_order, pay=pay, direction="in")
        return

    out_order = OutOrder.objects.select_related(
        "status",
        "solution__merchant__user",
        "solution__payment_system__currency",
        "pay_out__status",
    ).filter(id=deal_id).first()
    if out_order:
        pay = out_order.pay_out.first()
        _print_order_block(title=str(out_order.id), order=out_order, pay=pay, direction="out")
        return

    print(f"=== {deal_id} ===")
    print("NOT FOUND (ни PayIn, PayOut, InOrder, OutOrder)")
    print()


def main() -> None:
    raw = os.environ.get("DEAL_IDS", "").strip()
    ids = [part.strip() for part in raw.split(",") if part.strip()] if raw else list(DEFAULT_IDS)
    print(f"Deal rate info ({len(ids)} id(s))\n")
    for deal_id in ids:
        _lookup(deal_id)


main()
