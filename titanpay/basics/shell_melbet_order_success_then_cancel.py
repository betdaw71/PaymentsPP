"""
Откат Completed pay-in: revert проводок + Cancelled + Failed callback мерчанту.

Ищет заявку по PayIn UUID или merchant_order_id.

Запуск на сервере (pandapay пример):
  # 1) посмотреть состояние
  docker compose exec -T \\
    -e PAYIN_ID=6b6ccf00-3ecc-49db-abce-cbfae3f0d327 \\
    -e ACTION=inspect \\
    app python manage.py shell < titanpay/basics/shell_melbet_order_success_then_cancel.py

  # 2) dry-run отмены
  docker compose exec -T \\
    -e PAYIN_ID=6b6ccf00-3ecc-49db-abce-cbfae3f0d327 \\
    -e ACTION=cancel \\
    -e DRY_RUN=1 \\
    app python manage.py shell < titanpay/basics/shell_melbet_order_success_then_cancel.py

  # 3) боевая отмена + возврат средств + Failed callback
  docker compose exec -T \\
    -e PAYIN_ID=6b6ccf00-3ecc-49db-abce-cbfae3f0d327 \\
    -e ACTION=cancel \\
    app python manage.py shell < titanpay/basics/shell_melbet_order_success_then_cancel.py

Интерактивно:
  docker compose exec app python manage.py shell
  exec(open("titanpay/basics/shell_melbet_order_success_then_cancel.py").read())
  inspect("6b6ccf00-3ecc-49db-abce-cbfae3f0d327")
  step2_cancel("6b6ccf00-3ecc-49db-abce-cbfae3f0d327", dry_run=True)
  step2_cancel("6b6ccf00-3ecc-49db-abce-cbfae3f0d327")
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from payments.models import PayIn, PayInStatus
from payments.psp_payin import complete_inorder_from_psp_webhook, is_psp_trader
from trade.models import InOrder, InOrderStatus, InOrderStatusChange, Transaction, TransactionType

DEFAULT_LOOKUP = "6b6ccf00-3ecc-49db-abce-cbfae3f0d327"
COMPLETION_COMMENTS = frozenset({"In-order completed", "Commission", "Teamlead commission"})
SHELL_FREEZE_COMMENT = "Shell: top-up freeze before complete"
UNFREEZE_COMMENT = "Revert completed pay-in"


def _psp_balances(order: InOrder) -> tuple[Decimal, Decimal]:
    from basics.models import Balance

    if not order.payment_details_id:
        return Decimal("0"), Decimal("0")
    trader = order.payment_details.group.trader
    frozen = Balance.objects.get(pk=trader.frozen_balance_usdt_id).amount
    available = Balance.objects.get(pk=trader.balance_usdt_id).amount
    return frozen, available


def _count_unreversed_freezes(order: InOrder) -> int:
    count = 0
    for fz in Transaction.objects.filter(linked_in_order=order, transaction_type__name="Freeze"):
        reversed_ = Transaction.objects.filter(
            linked_in_order=order,
            transaction_type__name="Deposit",
            from_balance=fz.to_balance,
            to_balance=fz.from_balance,
            creation_date__gte=fz.creation_date,
        ).exists()
        if not reversed_:
            count += 1
    return count


def _resync_payin_before_complete(pay_in: PayIn, order: InOrder) -> None:
    """PayIn Failed при InOrder New — типично после fail webhook без отмены InOrder."""
    in_ok = order.status and order.status.name in {"New", "Money sent by user", "Expired", "Cancelled", "Arbitrage"}
    pay_bad = pay_in.status and pay_in.status.name in {"Failed", "Declined"}
    if not (in_ok and pay_bad):
        return
    print(f"[step1] resync PayIn {pay_in.status.name} -> In Progress (InOrder still {order.status.name})")
    pay_in.status = PayInStatus.objects.get(name="In Progress")
    pay_in.updated_at = timezone.now()
    pay_in.save(update_fields=["status", "updated_at"])


def _top_up_psp_frozen_if_needed(order: InOrder, *, dry_run: bool = False) -> None:
    if not order.payment_details_id or not is_psp_trader(order.payment_details.group.trader):
        return
    from basics.models import Balance

    trader = order.payment_details.group.trader
    need = Decimal(str(order.usd_amount))
    frozen_bal = Balance.objects.select_for_update().get(pk=trader.frozen_balance_usdt_id)
    available_bal = Balance.objects.select_for_update().get(pk=trader.balance_usdt_id)
    if frozen_bal.amount >= need:
        print(f"[step1] PSP frozen OK: {frozen_bal.amount} >= {need}")
        return
    shortfall = need - frozen_bal.amount
    print(
        f"[step1] PSP frozen insufficient: frozen={frozen_bal.amount}, need={need}, "
        f"top-up {shortfall} from available={available_bal.amount}"
    )
    if available_bal.amount < shortfall:
        raise ValueError(
            f"PSP trader {trader.user.username}: cannot top-up freeze "
            f"(need={need}, frozen={frozen_bal.amount}, available={available_bal.amount})"
        )
    if dry_run:
        return
    freeze_type = TransactionType.objects.get(name="Freeze")
    Transaction.create(
        _from=available_bal,
        _to=frozen_bal,
        value=shortfall,
        _transaction_type=freeze_type,
        _linked_in_order=order,
        _comment=SHELL_FREEZE_COMMENT,
    )


def _unfreeze_all_for_order(order: InOrder, comment: str) -> None:
    for i in range(5):
        remaining = _count_unreversed_freezes(order)
        if remaining == 0:
            break
        print(f"[step2] unfreeze pass {i + 1}, unreversed freezes={remaining}")
        order.unfreeze(comment)
    if _count_unreversed_freezes(order):
        print("[step2] warning: some Freeze txs still unreversed — check balances manually")


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _get_order(lookup: str) -> tuple[PayIn, InOrder]:
    lookup = str(lookup).strip()
    qs = PayIn.objects.select_related(
        "status",
        "order__status",
        "order__payment_details__group__trader__user",
        "merchant__user",
        "melbet_session",
        "protocol_session",
    )
    if _looks_like_uuid(lookup):
        pay_in = qs.filter(id=lookup).first()
        if pay_in is None:
            raise PayIn.DoesNotExist(f"PayIn id={lookup!r} not found")
    else:
        pay_in = qs.filter(merchant_order_id=lookup).first()
        if pay_in is None:
            raise PayIn.DoesNotExist(f"PayIn merchant_order_id={lookup!r} not found")
    if pay_in.order_id is None:
        raise ValueError(f"PayIn {pay_in.id} has no linked InOrder")
    return pay_in, pay_in.order


def inspect(lookup: str = DEFAULT_LOOKUP) -> dict:
    pay_in, order = _get_order(lookup)
    trader = None
    if order.payment_details_id:
        trader = order.payment_details.group.trader.user.username
    info = {
        "pay_in_id": str(pay_in.id),
        "in_order_id": str(order.id),
        "merchant": getattr(pay_in.merchant.user, "username", None),
        "merchant_order_id": pay_in.merchant_order_id,
        "pay_in_status": pay_in.status.name if pay_in.status else None,
        "in_order_status": order.status.name if order.status else None,
        "amount": str(pay_in.amount),
        "currency": pay_in.currency.symbol if pay_in.currency else None,
        "payment_system": pay_in.payment_system.name if pay_in.payment_system else None,
        "trader": trader,
        "melbet_order_id": getattr(getattr(pay_in, "melbet_session", None), "order_id", None),
        "protocol_session": bool(getattr(pay_in, "protocol_session", None)),
        "callback_url": pay_in.callback_url,
        "already_reverted": _already_reverted(order),
    }
    frozen, available = _psp_balances(order)
    info["trader_frozen_usdt"] = str(frozen)
    info["trader_available_usdt"] = str(available)
    info["order_usd_amount"] = str(order.usd_amount)
    txs = list(
        Transaction.objects.filter(linked_in_order=order)
        .select_related("transaction_type", "from_balance", "to_balance")
        .order_by("creation_date")
    )
    print("=" * 60)
    for k, v in info.items():
        print(f"  {k}: {v}")
    print(f"  linked_transactions: {len(txs)}")
    for tx in txs:
        print(
            f"    - {tx.creation_date:%Y-%m-%d %H:%M:%S} "
            f"{tx.transaction_type.name if tx.transaction_type else '?'} "
            f"{tx.value} [{tx.comment}]"
        )
    print("=" * 60)
    return info


def _completion_transactions(order: InOrder):
    return list(
        Transaction.objects.filter(
            linked_in_order=order,
            comment__in=COMPLETION_COMMENTS,
        )
        .select_related("transaction_type", "from_balance", "to_balance")
        .order_by("creation_date")
    )


def _already_reverted(order: InOrder) -> bool:
    return Transaction.objects.filter(
        linked_in_order=order,
        comment__startswith="Revert:",
    ).exists()


def _finalize_cancel_payin(pay_in: PayIn) -> None:
    failed = PayInStatus.objects.get(name="Failed")
    pay_in.status = failed
    pay_in.updated_at = timezone.now()
    pay_in.save(update_fields=["status", "updated_at"])
    pay_in.send_callback({"status": "Failed"})
    print("[step2] PayIn -> Failed, merchant callback sent")


@transaction.atomic
def step1_success(lookup: str = DEFAULT_LOOKUP, *, dry_run: bool = False) -> None:
    """Завершить заявку (если ещё не Completed) и отправить Success callback."""
    pay_in, order = _get_order(lookup)
    order = InOrder.objects.select_for_update().get(pk=order.pk)
    pay_in = PayIn.objects.select_for_update().get(pk=pay_in.pk)
    print(f"[step1] InOrder={order.status.name if order.status else None}, PayIn={pay_in.status.name if pay_in.status else None}")
    if order.status and order.status.name == "Completed":
        print("[step1] already Completed — only resend Success callback")
        if dry_run:
            print("[step1] dry_run: would send_callback Success")
            return
        pay_in.send_callback({"status": "Success"})
        print("[step1] callback sent")
        return
    allowed = {"New", "Money sent by user", "Expired", "Cancelled", "Arbitrage"}
    if order.status.name not in allowed:
        raise ValueError(f"InOrder status {order.status.name!r} cannot be completed")
    if dry_run:
        _resync_payin_before_complete(pay_in, order)
        _top_up_psp_frozen_if_needed(order, dry_run=True)
        print(f"[step1] dry_run: would complete_from_psp_success from {order.status.name}")
        return
    _resync_payin_before_complete(pay_in, order)
    _top_up_psp_frozen_if_needed(order)
    complete_inorder_from_psp_webhook(order, None)
    pay_in.refresh_from_db()
    order.refresh_from_db()
    print(f"[step1] done: InOrder={order.status.name}, PayIn={pay_in.status.name}")


@transaction.atomic
def step2_cancel(lookup: str = DEFAULT_LOOKUP, *, dry_run: bool = False) -> None:
    """
    Откатить проводки complete(), вернуть InOrder в Cancelled, PayIn → Failed,
    отправить Failed callback. Балансы возвращаются к состоянию «до complete».
    """
    pay_in, order = _get_order(lookup)
    order = InOrder.objects.select_for_update().get(pk=order.pk)
    pay_in = PayIn.objects.select_for_update().get(pk=pay_in.pk)
    print(f"[step2] InOrder={order.status.name if order.status else None}, PayIn={pay_in.status.name if pay_in.status else None}")
    if order.status and order.status.name == "Cancelled":
        print("[step2] already Cancelled")
        if dry_run:
            print("[step2] dry_run: would set PayIn Failed + send_callback Failed")
            return
        if pay_in.status and pay_in.status.name != "Failed":
            _finalize_cancel_payin(pay_in)
        else:
            pay_in.send_callback({"status": "Failed"})
            print("[step2] Failed callback resent")
        return
    if order.status and order.status.name != "Completed":
        raise ValueError(f"Expected Completed before cancel-revert, got {order.status.name!r}")
    completion_txs = _completion_transactions(order)
    if not completion_txs:
        raise ValueError("No completion transactions found — cannot safely revert accounting")
    if _already_reverted(order):
        raise ValueError("Revert transactions already exist for this order — aborting to avoid double revert")
    charge_type = TransactionType.objects.get(name="Charge")
    deposit_type = TransactionType.objects.get(name="Deposit")
    print(f"[step2] will revert {len(completion_txs)} completion transaction(s)")
    for tx in completion_txs:
        reverse_type = deposit_type if tx.transaction_type.name == "Charge" else charge_type
        print(
            f"  revert {tx.transaction_type.name} {tx.value} "
            f"({tx.from_balance_id} -> {tx.to_balance_id}) as {reverse_type.name}"
        )
    if dry_run:
        print("[step2] dry_run: would also unfreeze, decrease volumes, set Cancelled, PayIn Failed + callback")
        return
    for tx in reversed(completion_txs):
        reverse_type = deposit_type if tx.transaction_type.name == "Charge" else charge_type
        Transaction.create(
            _from=tx.to_balance,
            _to=tx.from_balance,
            value=tx.value,
            _transaction_type=reverse_type,
            _linked_in_order=order,
            _comment=f"Revert: {tx.comment}",
        )
    if order.payment_details_id:
        group = order.payment_details.group
        group.total_volume = (group.total_volume or Decimal("0")) - order.amount
        group.save(update_fields=["total_volume"])
        order.decrease_current_volume()
    _unfreeze_all_for_order(order, UNFREEZE_COMMENT)
    cancelled = InOrderStatus.objects.get(name="Cancelled")
    order.status = cancelled
    order.updated_date = timezone.now()
    order.save(update_fields=["status", "updated_date"])
    InOrderStatusChange.create(order=order, status=cancelled)
    pay_in.refresh_from_db()
    order.refresh_from_db()
    _finalize_cancel_payin(pay_in)
    print(f"[step2] done: InOrder={order.status.name}, PayIn={pay_in.status.name}")


def run_both(lookup: str = DEFAULT_LOOKUP, *, dry_run: bool = False) -> None:
    step1_success(lookup, dry_run=dry_run)
    if not dry_run:
        step2_cancel(lookup, dry_run=False)


def main() -> None:
    lookup = (
        os.environ.get("PAYIN_ID", "").strip()
        or os.environ.get("MERCHANT_ORDER_ID", "").strip()
        or DEFAULT_LOOKUP
    )
    action = os.environ.get("ACTION", "inspect").strip().lower()
    dry_run = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")
    print(f"lookup={lookup} action={action} dry_run={dry_run}\n")
    if action == "inspect":
        inspect(lookup)
    elif action == "cancel":
        step2_cancel(lookup, dry_run=dry_run)
    elif action == "success":
        step1_success(lookup, dry_run=dry_run)
    elif action == "both":
        run_both(lookup, dry_run=dry_run)
    else:
        raise ValueError(f"Unknown ACTION={action!r} (inspect|cancel|success|both)")


if os.environ.get("INTERACTIVE", "").strip() in ("1", "true", "yes"):
    print("Loaded. Commands: inspect(), step1_success(), step2_cancel(), run_both()")
else:
    main()
