"""
Демо KZT (melbet_test): несколько pay-in / pay-out — complete, cancel, expire, перерасчёт.

Требования на стенде:
  - melbet_test + C2CKZT solution (shell_create_melbet_test_merchant.py)
  - активный трейдер с реквизитами C2CKZT и USDT на freeze (для complete)
  - prepaid KZT при необходимости (shell_melbet_kzt_balance.py)

Запуск:
  docker compose exec app python manage.py shell -c "exec(open('basics/shell_melbet_kzt_order_demo.py').read()); run()"

Или:
  exec(open('basics/shell_melbet_kzt_order_demo.py').read())
  diagnose()
  run(dry_run=True)
  run()
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from basics.models import Balance, Currency, PaymentSystem, PaymentDetailsGroup
from merchant.kzt_settlement import (
    ensure_kzt_balances,
    in_order_credit_kzt,
    is_melbet_merchant,
    merchant_fee_in_kzt,
    uses_melbet_kzt_settlement,
)
from merchant.models import Merchant, MerchantSolution
from payments.models import PayIn, PayInStatus, PayOut, PayOutStatus
from payments.psp_payin import decline_payin, is_psp_trader
from payments.utils2 import assert_payin_amount_within_solution, check_pending, get_client_object
from trade.models import InOrder, OutOrder, Transaction, TransactionType, TraderTeamRates

MERCHANT_USERNAME = "melbet_test"
FTD = False
PS_NAME = "C2CKZT"
RUN_ID = int(time.time())


def _merchant() -> Merchant:
    user = User.objects.filter(username=MERCHANT_USERNAME).first()
    if user is None or not hasattr(user, "merchant"):
        raise RuntimeError(f"Merchant {MERCHANT_USERNAME!r} not found — run shell_create_melbet_test_merchant.py")
    m = user.merchant
    if not is_melbet_merchant(m):
        raise RuntimeError(f"{MERCHANT_USERNAME} is not in MELBET_KZT_USERNAMES")
    ensure_kzt_balances(m)
    m.refresh_from_db()
    return m


def _solution(merchant: Merchant) -> MerchantSolution:
    sol = (
        MerchantSolution.objects.filter(
            merchant=merchant,
            payment_system__name__iexact=PS_NAME,
            ftd=FTD,
            status=1,
        )
        .select_related("payment_system", "payment_system__currency")
        .first()
    )
    if sol is None:
        raise RuntimeError(f"No active MerchantSolution for {PS_NAME} ftd={FTD}")
    return sol


def _currency_ps(solution: MerchantSolution) -> tuple[Currency, PaymentSystem]:
    ps = solution.payment_system
    return ps.currency, ps


def _order_id(tag: str) -> str:
    return f"kztdemo-{RUN_ID}-{tag}"


def _client(merchant: Merchant, tag: str):
    payload = {
        "client_id": f"demo-{RUN_ID}-{tag}",
        "email": f"demo-{RUN_ID}-{tag}@test.invalid",
        "phone": f"+7705{abs(hash(tag)) % 10**7:07d}",
        "name": "KZT Demo Client",
    }
    client, ok = get_client_object(payload, merchant)
    if not ok:
        raise RuntimeError("Client blacklisted")
    return client


def _trader_usdt(trader) -> tuple[Decimal, Decimal]:
    if trader is None:
        return Decimal("0"), Decimal("0")
    av = Balance.objects.get(pk=trader.balance_usdt_id).amount
    fr = Balance.objects.get(pk=trader.frozen_balance_usdt_id).amount
    return av, fr


def balances(title: str = "", *, merchant: Merchant | None = None, trader=None) -> dict:
    merchant = merchant or _merchant()
    ensure_kzt_balances(merchant)
    merchant.refresh_from_db()
    row = {
        "merchant_kzt": merchant.balance_kzt.amount,
        "merchant_kzt_frozen": merchant.frozen_balance_kzt.amount,
        "merchant_usdt": merchant.balance.amount if merchant.balance else Decimal("0"),
        "merchant_usdt_frozen": merchant.frozen_balance.amount if merchant.frozen_balance else Decimal("0"),
    }
    if trader is not None:
        av, fr = _trader_usdt(trader)
        row["trader"] = trader.user.username
        row["trader_usdt"] = av
        row["trader_usdt_frozen"] = fr
    print("--- balances" + (f" [{title}]" if title else "") + " ---")
    for k, v in row.items():
        print(f"  {k}: {v}")
    return row


def diagnose() -> None:
    merchant = _merchant()
    sol = _solution(merchant)
    groups = PaymentDetailsGroup.objects.filter(
        payment_system__name__iexact=PS_NAME,
        status=1,
    ).select_related("trader__user")
    print("=" * 60)
    print(f"Merchant: {MERCHANT_USERNAME} id={merchant.id}")
    print(f"Solution: {PS_NAME} mdr_in={sol.mdr_in}% limits in {sol.min_limit_in}–{sol.max_limit_in}")
    print(f"C2CKZT groups (status=1): {groups.count()}")
    from django.conf import settings

    pref = (getattr(settings, "MELBET_KZT_TEST_TRADER_USERNAME", None) or "").strip()
    if pref:
        print(f"Routing preference (env): {pref}")
    for g in groups[:10]:
        print(f"  trader={g.trader.user.username} volume={g.current_volume} owner={g.owner!r}")
    balances("diagnose")
    print("=" * 60)


def _top_up_trader_freeze(order: InOrder) -> None:
    if not order.payment_details_id:
        return
    trader = order.payment_details.group.trader
    if not is_psp_trader(trader):
        return
    need = Decimal(str(order.usd_amount))
    frozen_bal = Balance.objects.select_for_update().get(pk=trader.frozen_balance_usdt_id)
    if frozen_bal.amount >= need:
        return
    shortfall = need - frozen_bal.amount
    available_bal = Balance.objects.select_for_update().get(pk=trader.balance_usdt_id)
    if available_bal.amount < shortfall:
        raise ValueError(
            f"Trader {trader.user.username}: need {need} USDT frozen, "
            f"have frozen={frozen_bal.amount} available={available_bal.amount}"
        )
    freeze_type = TransactionType.objects.get(name="Freeze")
    Transaction.create(
        _from=available_bal,
        _to=frozen_bal,
        value=shortfall,
        _transaction_type=freeze_type,
        _linked_in_order=order,
        _comment="KZT demo: top-up PSP freeze",
    )


@transaction.atomic
def create_payin(amount: Decimal | str, tag: str) -> PayIn | None:
    amount = Decimal(str(amount))
    merchant = _merchant()
    solution = _solution(merchant)
    assert_payin_amount_within_solution(solution, amount)
    currency, ps = _currency_ps(solution)
    moid = _order_id(tag)
    if InOrder.objects.filter(solution__merchant=merchant, merchant_order_id=moid).exists():
        raise ValueError(f"merchant_order_id exists: {moid}")
    client = _client(merchant, tag)
    if check_pending(client, _in=True):
        raise ValueError("Client has pending pay-in")
    in_order = InOrder.create(
        amount=amount,
        solution=solution,
        client_deposit_count=client.order_count,
        merchant_order_id=moid,
    )
    pay_in = PayIn.objects.create(
        amount=amount,
        currency=currency,
        payment_system=ps,
        merchant_order_id=moid,
        callback_url="https://example.invalid/kzt-demo",
        merchant=merchant,
        order=in_order,
        status=PayInStatus.objects.get(name="In Progress"),
        client=client,
    )
    print(
        f"[create_payin {tag}] amount={amount} status={in_order.status.name} "
        f"trader={getattr(getattr(in_order.payment_details, 'group', None), 'trader', None)}"
    )
    if in_order.status.name == "Cannot process":
        decline_payin(pay_in, send_callback=False)
        print(f"  -> Cannot process (нет реквизитов / freeze)")
        return pay_in
    return pay_in


def _get_payin(moid: str) -> tuple[PayIn, InOrder]:
    pay_in = PayIn.objects.select_related("order__status", "merchant__user").get(merchant_order_id=moid)
    if pay_in.order_id is None:
        raise ValueError("No InOrder")
    return pay_in, pay_in.order


def _complete_inorder_kzt(order: InOrder, paid_amount: Decimal | None = None) -> None:
    paid = Decimal(str(paid_amount)) if paid_amount is not None else order.amount
    paid = paid.quantize(Decimal("0.01"))
    if not uses_melbet_kzt_settlement(order.solution.merchant, order.solution.payment_system):
        if paid != order.amount:
            order.complete_from_psp_success(paid)
        else:
            order.complete_after_new()
        return
    rate = order.solution.payment_system.get_rate()
    team_rate = TraderTeamRates.objects.get(
        team=order.payment_details.group.trader.team,
        payment_system=order.solution.payment_system,
    )
    if paid != order.amount:
        order.unfreeze("KZT demo recalc")
        order.amount = paid
        order.usd_amount = (paid / Decimal(str(rate))).quantize(Decimal("0.01"))
        order.merchant_fee = merchant_fee_in_kzt(paid, order.solution.mdr_in)
        order.trader_fee = (team_rate.mdr_in * order.usd_amount / Decimal(100)).quantize(Decimal("0.01"))
        order.recalculated = True
        order.recalculated_amount = paid
        order.save()
        pay_in = order.pay_in.get()
        pay_in.amount = paid
        pay_in.recalculated = True
        pay_in.save(update_fields=["amount", "recalculated", "updated_at"])
        order.freeze("KZT demo recalc")
    _top_up_trader_freeze(order)
    order.complete()


@transaction.atomic
def complete_payin(moid: str, paid_amount: Decimal | str | None = None) -> None:
    pay_in, order = _get_payin(moid)
    order = InOrder.objects.select_for_update().get(pk=order.pk)
    print(f"[complete] {moid} InOrder={order.status.name} amount={order.amount}")
    if order.status.name == "Completed":
        print("  already Completed")
        return
    if order.status.name not in ("New", "Money sent by user", "Expired", "Cancelled", "Arbitrage"):
        raise ValueError(f"Cannot complete from {order.status.name}")
    if order.status.name == "Expired":
        if paid_amount is not None and Decimal(str(paid_amount)) != order.amount:
            order.apply_psp_paid_amount_recalc(Decimal(str(paid_amount)))
        order.complete_after_expired()
        return
    _complete_inorder_kzt(order, paid_amount)
    pay_in.refresh_from_db()
    order.refresh_from_db()
    credit = in_order_credit_kzt(order) if order.status.name == "Completed" else None
    print(f"  -> InOrder={order.status.name} PayIn={pay_in.status.name} merchant_credit_kzt≈{credit}")


@transaction.atomic
def cancel_payin(moid: str) -> None:
    pay_in, order = _get_payin(moid)
    order = InOrder.objects.select_for_update().get(pk=order.pk)
    print(f"[cancel] {moid} InOrder={order.status.name}")
    if order.status.name != "New":
        raise ValueError("cancel only from New")
    order.cancel_order()
    pay_in.refresh_from_db()
    print(f"  -> InOrder={order.status.name} PayIn={pay_in.status.name}")


@transaction.atomic
def expire_payin(moid: str) -> None:
    pay_in, order = _get_payin(moid)
    order = InOrder.objects.select_for_update().get(pk=order.pk)
    print(f"[expire] {moid} InOrder={order.status.name}")
    if order.status.name not in ("New", "Money sent by user"):
        raise ValueError("expire from New or Money sent by user")
    order.deal_time_expired()
    pay_in.refresh_from_db()
    print(f"  -> InOrder={order.status.name} PayIn={pay_in.status.name}")


def _payout_details(payment_system: PaymentSystem, card: str) -> dict:
    """Строго только ключи из payment_system.required_fields (без owner/bank «сверху»)."""
    fields = payment_system.required_fields if isinstance(payment_system.required_fields, dict) else {}
    if not fields:
        return {"card_number": card}
    out: dict[str, str] = {}
    for key in fields:
        if key == "card_number":
            out[key] = card
        elif key == "phone":
            out[key] = "+77051112233"
        else:
            out[key] = "demo"
    return out


@transaction.atomic
def create_payout(amount: Decimal | str, tag: str, card: str = "4111111111111111") -> PayOut | None:
    amount = Decimal(str(amount))
    merchant = _merchant()
    solution = _solution(merchant)
    if not (solution.min_limit_out <= amount <= solution.max_limit_out):
        raise ValueError("Amount out of payout limits")
    currency, ps = _currency_ps(solution)
    moid = _order_id(f"out-{tag}")
    client = _client(merchant, f"out-{tag}")
    if check_pending(client, _in=False):
        raise ValueError("Client has pending pay-out")
    details = _payout_details(ps, card)
    out_order = OutOrder.create(
        amount=amount,
        solution=solution,
        details=details,
        merchant_order_id=moid,
    )
    pay_out = PayOut.objects.create(
        amount=amount,
        currency=currency,
        payment_system=ps,
        merchant_order_id=moid,
        callback_url="https://example.invalid/kzt-demo-out",
        merchant=merchant,
        order=out_order,
        status=PayOutStatus.objects.get(name="New"),
        details=details,
        client=client,
    )
    print(f"[create_payout {tag}] amount={amount} OutOrder={out_order.status.name} merchant_order_id={moid}")
    if out_order.status.name == "Cannot process":
        pay_out.declined()
        return pay_out
    return pay_out


@transaction.atomic
def payout_and_complete(amount: Decimal | str = "5000", tag: str = "p1") -> None:
    """Создать pay-out и завершить (без плейсхолдера kztdemo-... в id)."""
    po = create_payout(amount, tag)
    if po is None:
        return
    if po.order_id and po.order.status.name == "New":
        complete_payout(po.merchant_order_id)
        trader = None
        if po.order.payment_details_id:
            trader = po.order.payment_details.group.trader
        balances("after payout_and_complete", trader=trader)


@transaction.atomic
def complete_payout(moid: str) -> None:
    pay_out = PayOut.objects.select_related("order").get(merchant_order_id=moid)
    order = OutOrder.objects.select_for_update().get(pk=pay_out.order_id)
    print(f"[complete_payout] {moid} OutOrder={order.status.name}")
    if order.status.name == "Completed":
        return
    if order.status.name == "New":
        order.money_sent()
    order.complete_after_money_sent()
    pay_out.refresh_from_db()
    print(f"  -> OutOrder={order.status.name} PayOut={pay_out.status.name}")


@transaction.atomic
def cancel_payout(moid: str) -> None:
    pay_out = PayOut.objects.select_related("order").get(merchant_order_id=moid)
    order = OutOrder.objects.select_for_update().get(pk=pay_out.order_id)
    print(f"[cancel_payout] {moid} OutOrder={order.status.name}")
    if order.status.name != "New":
        raise ValueError("cancel payout only from New")
    order.deal_expired()
    pay_out.refresh_from_db()
    print(f"  -> OutOrder={order.status.name} (may spawn retry OutOrder)")


def _last_trader_from_payin(pay_in: PayIn | None):
    if pay_in and pay_in.order and pay_in.order.payment_details_id:
        return pay_in.order.payment_details.group.trader
    return None


def run(*, dry_run: bool = False, payin_amount: str = "10000", recalc_amount: str = "9500") -> None:
    """
    Сценарий:
      1) pay-in complete на номинал
      2) pay-in cancel
      3) pay-in expire → complete с перерасчётом
      4) pay-in complete с перерасчётом с New
      5) pay-out complete
      6) pay-out cancel (expire)
    """
    global RUN_ID
    RUN_ID = int(time.time())
    diagnose()
    if dry_run:
        print("dry_run: только diagnose(), заявки не создаются")
        return

    amt = Decimal(payin_amount)
    rec = Decimal(recalc_amount)
    merchant = _merchant()
    trader = None

    balances("start", merchant=merchant)

    p1 = create_payin(amt, "complete")
    trader = _last_trader_from_payin(p1)
    balances("after create #1", merchant=merchant, trader=trader)
    if p1 and p1.order.status.name == "New":
        complete_payin(p1.merchant_order_id)
        balances("after complete #1", merchant=merchant, trader=trader)

    p2 = create_payin(amt, "cancel")
    trader = _last_trader_from_payin(p2) or trader
    if p2 and p2.order.status.name == "New":
        cancel_payin(p2.merchant_order_id)
        balances("after cancel #2", merchant=merchant, trader=trader)

    p3 = create_payin(amt, "expire-recalc")
    trader = _last_trader_from_payin(p3) or trader
    if p3 and p3.order.status.name == "New":
        expire_payin(p3.merchant_order_id)
        complete_payin(p3.merchant_order_id, paid_amount=rec)
        balances("after expire+recalc #3", merchant=merchant, trader=trader)

    p4 = create_payin(amt, "new-recalc")
    trader = _last_trader_from_payin(p4) or trader
    if p4 and p4.order.status.name == "New":
        complete_payin(p4.merchant_order_id, paid_amount=rec)
        balances("after new+recalc #4", merchant=merchant, trader=trader)

    out_amt = min(amt, Decimal("5000"))
    po1 = create_payout(out_amt, "complete")
    if po1 and po1.order and po1.order.status.name == "New":
        complete_payout(po1.merchant_order_id)
        balances("after payout complete", merchant=merchant, trader=trader)

    po2 = create_payout(out_amt, "cancel")
    if po2 and po2.order and po2.order.status.name == "New":
        cancel_payout(po2.merchant_order_id)
        balances("after payout cancel", merchant=merchant, trader=trader)

    print("=" * 60)
    print("DONE. Проверьте кабинет melbet_test и транзакции по merchant_order_id kztdemo-*")
    print("=" * 60)


if __name__ == "__main__":
    run()
else:
    print(
        "Loaded: diagnose(), balances(), create_payin(), complete_payin(), "
        "cancel_payin(), expire_payin(), create_payout(), complete_payout(), "
        "cancel_payout(), payout_and_complete(), run(), run(dry_run=True)"
    )
