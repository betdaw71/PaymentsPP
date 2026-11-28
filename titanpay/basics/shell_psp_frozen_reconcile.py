"""
PSP-трейдеры: диагностика frozen USDT и разморозка зависших Freeze.

Пример:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_psp_frozen_reconcile.py

Только диагностика:
  docker compose exec -T -e APPLY=0 app python manage.py shell < titanpay/basics/shell_psp_frozen_reconcile.py

Разморозить зависшие (терминальные InOrder с неоткатанным Freeze):
  docker compose exec -T -e APPLY=1 app python manage.py shell < titanpay/basics/shell_psp_frozen_reconcile.py

Конкретный трейдер:
  docker compose exec -T -e TRADER=botonpay1 -e APPLY=1 app python manage.py shell < titanpay/basics/shell_psp_frozen_reconcile.py
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.db import transaction

from basics.models import Trader
from payments.psp_payin import (
    _INORDER_OPEN_STATUSES,
    _INORDER_RELEASE_FREEZE_STATUSES,
    expected_psp_frozen_usdt,
    freeze_tx_is_reversed,
    inorder_ids_with_unreversed_freezes,
    is_psp_trader,
    psp_trader_frozen_snapshot,
    reconcile_stuck_psp_inorder_freezes,
)
from trade.models import InOrder, Transaction

TRADER = os.environ.get("TRADER", "").strip()
APPLY = os.environ.get("APPLY", "").strip() in ("1", "true", "yes")
LIMIT = int(os.environ.get("LIMIT", "50"))


def _psp_traders():
    qs = Trader.objects.select_related("user", "frozen_balance_usdt", "balance_usdt").filter(blocked=False)
    if TRADER:
        qs = qs.filter(user__username=TRADER)
    return [t for t in qs if is_psp_trader(t)]


def diagnose() -> None:
    print("=" * 72)
    print("PSP FROZEN DIAGNOSE")
    traders = _psp_traders()
    if not traders:
        print("No PSP traders found.")
        return

    total_stuck = Decimal("0")
    for trader in traders:
        snap = psp_trader_frozen_snapshot(trader)
        stuck = Decimal(str(snap["stuck_usdt"]))
        total_stuck += max(stuck, Decimal("0"))
        flag = " *** STUCK ***" if stuck > Decimal("1") else ""
        print(
            f"  {snap['trader']:16} frozen={snap['frozen_usdt']:>10} "
            f"available={snap['available_usdt']:>10} "
            f"expected={snap['expected_frozen_usdt']:>10} "
            f"delta={snap['stuck_usdt']:>10}{flag}"
        )

        open_orders = InOrder.objects.filter(
            payment_details__group__trader=trader,
            status__name__in=_INORDER_OPEN_STATUSES,
        ).count()
        print(f"    open InOrders (New): {open_orders}")

    orphan_ids = inorder_ids_with_unreversed_freezes()
    terminal_orphan = InOrder.objects.filter(
        id__in=orphan_ids,
        status__name__in=_INORDER_RELEASE_FREEZE_STATUSES,
    ).count()
    print(f"\n  InOrders with unreversed Freeze: {len(orphan_ids)}")
    print(f"  terminal (should release):       {terminal_orphan}")
    print(f"  total stuck delta (sum):         {total_stuck}")
    print("=" * 72)


def show_orphan_samples() -> None:
    order_ids = list(inorder_ids_with_unreversed_freezes())[:LIMIT]
    if not order_ids:
        print("No unreversed freezes.")
        return
    print(f"\n--- Orphan freeze samples (max {LIMIT}) ---")
    for order in InOrder.objects.filter(id__in=order_ids).select_related("status").order_by("-updated_date")[:LIMIT]:
        freezes = Transaction.objects.filter(linked_in_order=order, transaction_type__name="Freeze")
        unreversed = sum(1 for fz in freezes if not freeze_tx_is_reversed(fz))
        trader = None
        if order.payment_details_id:
            trader = order.payment_details.group.trader.user.username
        print(
            f"  in_order={order.id} status={order.status.name if order.status else '?'} "
            f"trader={trader} unreversed_freezes={unreversed} amount={order.amount}"
        )


def apply_reconcile() -> None:
    if not APPLY:
        print("\nDry-run. Set APPLY=1 to release stuck freezes on terminal InOrders.")
        return
    n = reconcile_stuck_psp_inorder_freezes(limit=500)
    print(f"\nReconciled {n} InOrder(s).")
    diagnose()


def main() -> None:
    diagnose()
    show_orphan_samples()
    apply_reconcile()


main()
