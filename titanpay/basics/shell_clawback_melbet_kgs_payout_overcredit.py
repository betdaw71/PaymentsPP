"""
Откат перекредита USDT тестовому трейдеру после Melbet KGS out
(когда trader_fee был в фиате, а complete зачислил usd+fiat как USDT).

  MERCHANT_ORDER_ID=w5547812021 \\
  docker compose exec -T -e MERCHANT_ORDER_ID app \\
    python manage.py shell < titanpay/basics/shell_clawback_melbet_kgs_payout_overcredit.py

  APPLY=1 — списать лишнее с трейдера на aggregator (type=2).
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.db import transaction

from basics.models import Balance, Trader
from payments.models import PayOut
from trade.models import OutOrder, Transaction, TransactionType

MOID = (os.environ.get("MERCHANT_ORDER_ID") or "w5547812021").strip()
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}


def _candidates(raw: str) -> list[str]:
    out = [raw]
    if raw.lower().startswith("w") and raw[1:].isdigit():
        out.append(raw[1:])
    elif raw.isdigit():
        out.extend([f"w{raw}", f"W{raw}"])
    return list(dict.fromkeys(out))


def main() -> None:
    po = None
    for oid in _candidates(MOID):
        po = PayOut.objects.filter(merchant_order_id=oid).select_related("order").first()
        if po:
            break
    if po is None or po.order_id is None:
        print(f"NOT FOUND PayOut {MOID}")
        return
    od: OutOrder = (
        OutOrder.objects.select_related(
            "payment_details__group__trader__user",
            "solution__payment_system",
        ).get(pk=po.order_id)
    )
    print(
        f"OutOrder={od.id} status={od.status.name if od.status_id else None} "
        f"amount={od.amount} usd={od.usd_amount} m_fee={od.merchant_fee} t_fee={od.trader_fee}"
    )
    if not od.payment_details_id:
        print("no payment_details")
        return
    trader: Trader = od.payment_details.group.trader
    print(f"trader={trader.user.username} usdt={trader.balance_usdt.amount if trader.balance_usdt_id else None}")

    usd = Decimal(str(od.usd_amount or 0))
    fee = Decimal(str(od.trader_fee or 0))
    amt = Decimal(str(od.amount or 0))
    if amt > 0 and usd > 0 and fee > usd:
        fee_usd = (fee * usd / amt).quantize(Decimal("0.01"))
        credited_wrong = usd + fee
        should = usd + fee_usd
        over = (credited_wrong - should).quantize(Decimal("0.01"))
        print(f"fee fiat={fee} → usd={fee_usd}")
        print(f"credited_wrong≈{credited_wrong} should≈{should} OVER={over}")
    else:
        print("trader_fee already looks like USDT — nothing to claw back by heuristic")
        return

    if over <= 0:
        print("no overcredit")
        return
    if not APPLY:
        print("DRY-RUN — set APPLY=1 to Charge over from trader → aggregator")
        return

    with transaction.atomic():
        agg = Balance.objects.select_for_update().get(type=2)
        bal = Balance.objects.select_for_update().get(pk=trader.balance_usdt_id)
        tt = TransactionType.objects.get(name="Charge")
        Transaction.create(
            _from=bal,
            _to=agg,
            value=over,
            _transaction_type=tt,
            _linked_out_order=od,
            _comment=f"Clawback Melbet KGS fiat trader_fee as USDT overcredit ({MOID})",
        )
        # normalize stored fee to USDT for future PnL/recalc
        od.trader_fee = fee_usd
        od.save(update_fields=["trader_fee"])
        bal.refresh_from_db()
        print(f"CHARGED {over} USDT; trader_fee now={od.trader_fee}; usdt={bal.amount}")


main()
