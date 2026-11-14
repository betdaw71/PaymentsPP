"""
Диагностика замороженного баланса живого трейдера (не только PSP).

Пример (resdfe):
  docker compose exec -T -e TRADER=resdfe app \\
    python manage.py shell < titanpay/basics/shell_diagnose_trader_frozen.py

Разморозить только терминальные cancel/expired с неоткатанным Freeze
(НЕ трогает Completed / New / Money sent / Arbitrage):
  docker compose exec -T -e TRADER=resdfe -e APPLY=1 app \\
    python manage.py shell < titanpay/basics/shell_diagnose_trader_frozen.py
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum as models_Sum
from django.utils import timezone

from appeals.models import PayInAppeal, PayInAppealStatus
from basics.models import Trader
from payments.psp_payin import freeze_tx_is_reversed
from trade.models import InOrder, Transaction, WithdrawalRequest

TRADER = os.environ.get("TRADER", "resdfe").strip() or "resdfe"
APPLY = os.environ.get("APPLY", "").strip().lower() in ("1", "true", "yes")
LIMIT = int(os.environ.get("LIMIT", "40"))

OPEN_STATUSES = frozenset({"New", "Money sent by user", "Arbitrage", "Recalculation"})
RELEASE_STATUSES = frozenset(
    {
        "Expired",
        "Cannot process",
        "Cancelled",
        "Cancelled by support",
        "Cancelled by trader",
        "Cancelled by user",
    }
)


def _msk(dt):
    if dt is None:
        return "-"
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M:%S %Z")


def _dec(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def _freeze_consumed_by_charge(freeze_tx) -> bool:
    return Transaction.objects.filter(
        linked_in_order_id=freeze_tx.linked_in_order_id,
        transaction_type__name="Charge",
        from_balance_id=freeze_tx.to_balance_id,
        creation_date__gte=freeze_tx.creation_date,
    ).exists()


def main() -> None:
    trader = (
        Trader.objects.select_related("user", "balance_usdt", "frozen_balance_usdt")
        .filter(user__username__iexact=TRADER)
        .first()
    )
    if trader is None:
        print(f"Trader {TRADER!r} not found")
        return

    frozen = _dec(trader.frozen_balance_usdt.amount)
    available = _dec(trader.balance_usdt.amount)

    print("=" * 72)
    print(f"TRADER FROZEN DIAGNOSE  trader={trader.user.username}  APPLY={int(APPLY)}")
    print("=" * 72)
    print(f"available:  {available} USDT")
    print(f"frozen:     {frozen} USDT")

    open_orders = list(
        InOrder.objects.filter(
            payment_details__group__trader=trader,
            status__name__in=OPEN_STATUSES,
        )
        .select_related("status", "payment_details__group")
        .order_by("-creation_date")
    )
    expected_orders = sum((_dec(o.usd_amount) for o in open_orders), Decimal("0"))

    pending_wd = list(
        WithdrawalRequest.objects.filter(from_user=trader.user, status=0).order_by("-date")
    )
    expected_wd = sum((_dec(w.amount) for w in pending_wd), Decimal("0"))
    expected = _dec(expected_orders + expected_wd)
    stuck = _dec(frozen - expected)

    print(f"expected:   {expected} USDT  (= open orders {expected_orders} + pending WD {expected_wd})")
    print(f"stuck Δ:    {stuck} USDT  {'*** STUCK ***' if stuck > Decimal('0.01') else '(ok)'}")

    print(f"\n--- Open InOrders holding freeze: n={len(open_orders)} ---")
    for o in open_orders[:LIMIT]:
        print(
            f"  {_msk(o.creation_date)}  {o.status.name:22}  "
            f"usd={_dec(o.usd_amount):>10}  fiat={_dec(o.amount):>12}  "
            f"id={o.id}"
        )
    if len(open_orders) > LIMIT:
        print(f"  ... +{len(open_orders) - LIMIT} more")

    print(f"\n--- Pending withdrawals: n={len(pending_wd)} ---")
    for w in pending_wd[:LIMIT]:
        print(f"  {_msk(w.date)}  amount={_dec(w.amount)}  to={w.address_to}  id={w.id}")

    open_appeals = list(
        PayInAppeal.objects.filter(
            Q(in_order__payment_details__group__trader=trader)
            | Q(pay_in__order__payment_details__group__trader=trader)
        )
        .exclude(
            status__in=(
                PayInAppealStatus.APPROVED,
                PayInAppealStatus.REJECTED,
                PayInAppealStatus.DUPLICATE,
            )
        )
        .select_related("in_order", "in_order__status", "pay_in")
        .order_by("-created_at")[:LIMIT]
    )
    print(f"\n--- Open appeals (not approved/rejected/dup): n={len(open_appeals)} ---")
    if not open_appeals:
        print("  (none)")
    for a in open_appeals:
        st = a.in_order.status.name if a.in_order and a.in_order.status else "?"
        print(
            f"  {_msk(a.created_at)}  appeal={a.status:18}  order_status={st:22}  "
            f"in_order={a.in_order_id}  pay_in={a.pay_in_id}"
        )

    # Ledger on frozen balance (explains the live amount)
    fid = trader.frozen_balance_usdt_id
    into = (
        Transaction.objects.filter(to_balance_id=fid).aggregate(s=models_Sum("value"))["s"]
        or Decimal("0")
    )
    outof = (
        Transaction.objects.filter(from_balance_id=fid).aggregate(s=models_Sum("value"))["s"]
        or Decimal("0")
    )
    print(f"\n--- Frozen ledger Σ ---")
    print(f"  credit (into frozen):  {_dec(into)}")
    print(f"  debit  (from frozen):  {_dec(outof)}")
    print(f"  net (should≈frozen):   {_dec(into - outof)}  actual={frozen}")

    # Unreversed Freeze on this trader's frozen balance (full scan)
    freezes = (
        Transaction.objects.filter(
            transaction_type__name="Freeze",
            to_balance_id=fid,
        )
        .select_related("linked_in_order", "linked_in_order__status")
        .order_by("-creation_date")
    )
    orphan_release = []
    orphan_completed_bookkeeping = []
    orphan_open = []
    orphan_other = []
    orphan_wd = []
    release_sum = Decimal("0")
    other_sum = Decimal("0")
    wd_sum = Decimal("0")
    for fz in freezes.iterator(chunk_size=200):
        if freeze_tx_is_reversed(fz):
            continue
        if fz.linked_in_order_id is None:
            orphan_wd.append(fz)
            wd_sum += _dec(fz.value)
            continue
        order = fz.linked_in_order
        st = order.status.name if order and order.status else "?"
        if _freeze_consumed_by_charge(fz):
            orphan_completed_bookkeeping.append((fz, st))
            continue
        if st in OPEN_STATUSES:
            orphan_open.append((fz, st))
        elif st in RELEASE_STATUSES:
            orphan_release.append((fz, st, order))
            release_sum += _dec(fz.value)
        else:
            orphan_other.append((fz, st, order))
            other_sum += _dec(fz.value)

    print(f"\n--- Unreversed Freeze on trader frozen balance ---")
    print(f"  open (expected):              {len(orphan_open)}")
    print(f"  terminal cancel/expired:      {len(orphan_release)}  sum≈{_dec(release_sum)}  ← can APPLY unfreeze")
    print(f"  completed+charged (ledger):   {len(orphan_completed_bookkeeping)}  ← do NOT unfreeze")
    print(f"  other statuses:               {len(orphan_other)}  sum≈{_dec(other_sum)}")
    print(f"  no linked_in_order (WD/etc):  {len(orphan_wd)}  sum≈{_dec(wd_sum)}")

    if orphan_release:
        print(f"\n--- Stuck freezes on terminal cancel/expired (max {LIMIT}) ---")
        for fz, st, order in orphan_release[:LIMIT]:
            print(
                f"  {_msk(fz.creation_date)}  status={st:22}  "
                f"freeze={_dec(fz.value):>10}  in_order={order.id}"
            )
        if len(orphan_release) > LIMIT:
            print(f"  ... +{len(orphan_release) - LIMIT} more")

    if orphan_other:
        print(f"\n--- Freezes on other statuses (max {LIMIT}) ---")
        for fz, st, order in orphan_other[:LIMIT]:
            oid = order.id if order else None
            print(
                f"  {_msk(fz.creation_date)}  status={st:22}  "
                f"freeze={_dec(fz.value):>10}  in_order={oid}"
            )

    if orphan_wd:
        print(f"\n--- Unreversed Freeze without InOrder (WD / manual) (max {LIMIT}) ---")
        for fz in orphan_wd[:LIMIT]:
            print(
                f"  {_msk(fz.creation_date)}  freeze={_dec(fz.value):>10}  "
                f"comment={fz.comment!r}  tx={fz.id}"
            )

    print(f"\nVERDICT:")
    print(f"  frozen={frozen} expected={expected} stuck={stuck}")
    print(f"  releasable_cancel_freeze_sum≈{_dec(release_sum)}")
    if orphan_release and _dec(release_sum) >= stuck - Decimal("0.05"):
        print("  → stuck объясняется cancel/expired Freeze; APPLY=1 вернёт на available")
    elif orphan_release:
        print("  → есть cancel/expired Freeze; APPLY=1 разморозит их (часть stuck может остаться)")
    elif orphan_wd and wd_sum > Decimal("0.01"):
        print("  → unreversed WD/manual Freeze без заявки — смотри комментарии выше (не авто-APPLY)")
    elif stuck > Decimal("0.01") and not open_orders and not pending_wd:
        print("  → frozen > 0 без open/WD; ledger net выше — нужна ручная проверка Charge/Deposit")
    elif stuck <= Decimal("0.01"):
        print("  → frozen объясняется открытыми заявками / WD")
    else:
        print("  → часть stuck может быть Completed-ledger или WD без linked_in_order")

    if not APPLY:
        print("\nDry-run. Set APPLY=1 to unfreeze terminal cancel/expired only.")
        return

    fixed = 0
    seen = set()
    for fz, st, order in orphan_release:
        if order.id in seen:
            continue
        seen.add(order.id)
        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=order.pk)
            if locked.status.name not in RELEASE_STATUSES:
                continue
            locked.unfreeze("Trader frozen reconcile (cancel/expired)")
            fixed += 1
    trader.frozen_balance_usdt.refresh_from_db()
    trader.balance_usdt.refresh_from_db()
    print(f"\nAPPLY done: unfroze {fixed} order(s)")
    print(
        f"balances now: available={_dec(trader.balance_usdt.amount)} "
        f"frozen={_dec(trader.frozen_balance_usdt.amount)}"
    )


main()
