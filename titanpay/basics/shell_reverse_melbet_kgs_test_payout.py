"""
Полный откат тестовой Melbet KGS выплаты (мерчант KGS + остаток USDT у трейдера).

После clawback overcredit у трейдера остаётся usd+fee_usdt, у Melbet kgs=-amount-m_fee.
Этот скрипт:
  1) возвращает Melbet balance_kgs += amount + merchant_fee
  2) списывает с трейдера оставшийся credit (usd_amount + trader_fee_usdt)

Статус OutOrder/PayOut по умолчанию НЕ меняем (у Melbet уже мог уйти Success CB).

  MERCHANT_ORDER_ID=w5547812021 \\
  docker compose exec -T -e MERCHANT_ORDER_ID app \\
    python manage.py shell < titanpay/basics/shell_reverse_melbet_kgs_test_payout.py

  APPLY=1 — выполнить проводки.
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.db import transaction

from basics.models import Balance
from merchant.kzt_settlement import merchant_available_balance
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


def _trader_fee_usd(od: OutOrder) -> Decimal:
    usd = Decimal(str(od.usd_amount or 0))
    fee = Decimal(str(od.trader_fee or 0))
    amt = Decimal(str(od.amount or 0))
    if amt > 0 and usd > 0 and fee > usd:
        return (fee * usd / amt).quantize(Decimal("0.01"))
    return fee.quantize(Decimal("0.01"))


def main() -> None:
    po = None
    for oid in _candidates(MOID):
        po = (
            PayOut.objects.filter(merchant_order_id=oid)
            .select_related("order", "merchant__user", "merchant__balance_kgs")
            .first()
        )
        if po:
            break
    if po is None or po.order_id is None:
        print(f"NOT FOUND PayOut {MOID}")
        return

    od = (
        OutOrder.objects.select_related(
            "payment_details__group__trader__user",
            "solution__merchant__user",
            "solution__payment_system",
        ).get(pk=po.order_id)
    )
    merchant = od.solution.merchant
    kgs_bal = merchant_available_balance(merchant, od.solution.payment_system)
    trader = od.payment_details.group.trader if od.payment_details_id else None

    amount = Decimal(str(od.amount or 0))
    m_fee = Decimal(str(od.merchant_fee or 0))
    kgs_restore = (amount + m_fee).quantize(Decimal("0.01"))
    usd = Decimal(str(od.usd_amount or 0)).quantize(Decimal("0.01"))
    t_fee_usd = _trader_fee_usd(od)
    trader_claw = (usd + t_fee_usd).quantize(Decimal("0.01"))

    print(f"PayOut={po.id} OutOrder={od.id} status={od.status.name if od.status_id else None}")
    print(f"merchant={merchant.user.username} kgs_now={kgs_bal.amount if kgs_bal else None}")
    print(f"  restore KGS +{kgs_restore} (= amount {amount} + m_fee {m_fee})")
    if trader:
        print(
            f"trader={trader.user.username} usdt={trader.balance_usdt.amount if trader.balance_usdt_id else None}"
        )
        print(f"  claw remaining USDT {trader_claw} (= usd {usd} + t_fee {t_fee_usd})")
    else:
        print("trader=None — only merchant KGS restore")

    if not APPLY:
        print("DRY-RUN — set APPLY=1 to reverse merchant KGS + remaining trader USDT")
        return

    with transaction.atomic():
        agg = Balance.objects.select_for_update().get(type=2)
        deposit = TransactionType.objects.get(name="Deposit")
        charge = TransactionType.objects.get(name="Charge")

        kgs = merchant_available_balance(merchant, od.solution.payment_system)
        kgs = Balance.objects.select_for_update().get(pk=kgs.id)
        # reverse complete Charge(frozen→agg): вернуть фиат на available KGS
        Transaction.create(
            _from=agg,
            _to=kgs,
            value=kgs_restore,
            _transaction_type=deposit,
            _linked_out_order=od,
            _comment=f"Reverse Melbet KGS test payout merchant ledger ({MOID})",
        )
        kgs.refresh_from_db()
        print(f"  Melbet kgs now={kgs.amount}")

        if trader and trader_claw > 0 and trader.balance_usdt_id:
            tbal = Balance.objects.select_for_update().get(pk=trader.balance_usdt_id)
            Transaction.create(
                _from=tbal,
                _to=agg,
                value=trader_claw,
                _transaction_type=charge,
                _linked_out_order=od,
                _comment=f"Reverse Melbet KGS test payout trader credit ({MOID})",
            )
            tbal.refresh_from_db()
            print(f"  trader usdt now={tbal.amount}")

    print("DONE — merchant KGS restored; trader remaining credit removed")
    print("  note: OutOrder/PayOut status left as-is (Melbet CB already sent)")


main()
