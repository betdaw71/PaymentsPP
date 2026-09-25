"""Melbet redirect: probe nearby amounts when routing/PSP cascade fails."""
from __future__ import annotations

import random
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from basics.models import TraderTeamRates
from merchant.kzt_settlement import is_melbet_merchant, merchant_fee_in_kzt, uses_melbet_kzt_settlement
from merchant.models import MerchantSolution
from payments.models import PayIn, PayInStatus
from payments.psp_payin import (
    _payin_has_psp_requisite,
    cancel_psp_if_linked,
    is_psp_trader,
)
from trade.models import InOrder, InOrderStatus
from trade.utils import choose_trader_in


def melbet_amount_probe_enabled(merchant) -> bool:
    if not is_melbet_merchant(merchant):
        return False
    return bool(getattr(settings, "MELBET_AMOUNT_PROBE_ENABLED", True))


def _parse_deltas(raw: str) -> list[int]:
    out: list[int] = []
    for part in str(raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def melbet_candidate_amounts(requested: Decimal, solution: MerchantSolution) -> list[Decimal]:
    """Original amount first, then nearby values within MerchantSolution limits."""
    requested = Decimal(str(requested)).quantize(Decimal("0.01"))
    if not melbet_amount_probe_enabled(solution.merchant):
        return [requested]

    deltas = _parse_deltas(getattr(settings, "MELBET_AMOUNT_PROBE_DELTAS", "20,-20,50,-50,100,-100"))
    max_extra = int(getattr(settings, "MELBET_AMOUNT_PROBE_MAX_EXTRA", "6"))
    if max_extra > 0:
        deltas = deltas[:max_extra]

    mn = Decimal(str(solution.min_limit_in))
    mx = Decimal(str(solution.max_limit_in))
    seen: set[Decimal] = set()
    ordered: list[Decimal] = []

    def _add(value: Decimal) -> None:
        value = value.quantize(Decimal("0.01"))
        if value <= 0 or value < mn or value > mx:
            return
        if value in seen:
            return
        seen.add(value)
        ordered.append(value)

    _add(requested)
    for delta in deltas:
        _add(requested + Decimal(delta))

    if len(ordered) <= 1:
        return ordered

    head, tail = ordered[0], ordered[1:]
    if getattr(settings, "MELBET_AMOUNT_PROBE_RANDOMIZE", True):
        random.shuffle(tail)
    return [head, *tail]


def is_melbet_deposit_allocated(pay_in: PayIn) -> bool:
    order = pay_in.order
    if order is None or not order.status:
        return False
    if order.status.name == "Cannot process":
        return False
    if pay_in.status and pay_in.status.name == "Declined":
        return False
    if order.payment_details_id is None:
        return False
    if order.status.name != "New":
        return False
    trader = order.payment_details.group.trader
    if is_psp_trader(trader):
        return _payin_has_psp_requisite(pay_in)
    return True


@transaction.atomic
def reallocate_melbet_in_order(
    pay_in: PayIn,
    new_amount: Decimal,
    solution: MerchantSolution,
    client,
) -> PayIn:
    """Retry routing for the same PayIn/InOrder with another amount."""
    new_amount = Decimal(str(new_amount)).quantize(Decimal("0.01"))
    pay_in = PayIn.objects.select_for_update().get(pk=pay_in.pk)
    order = InOrder.objects.select_for_update().get(pk=pay_in.order_id)

    if order.status and order.status.name not in {"Cannot process", "New"}:
        raise ValueError(f"Cannot reallocate InOrder in status {order.status.name!r}")

    cancel_psp_if_linked(pay_in)

    if order.payment_details_id and order.status.name == "New":
        order.decrease_current_volume()
        order.unfreeze("Melbet amount probe retry")

    active_orders = InOrder.objects.filter(
        status__name__in=["New", "Money sent by user"],
        amount=new_amount,
        solution__payment_system=solution.payment_system,
    ).exclude(pk=order.pk)

    chosen_detail, usd_amount, payment_system_obj, success = choose_trader_in(
        new_amount,
        solution.payment_system,
        solution.traffic,
        active_orders,
        client.order_count,
        merchant=solution.merchant,
    )

    order.amount = new_amount
    order.usd_amount = usd_amount
    order.payment_details = None
    order.updated_date = timezone.now()

    if not success:
        order.status = InOrderStatus.objects.get(name="Cannot process")
        order.save()
        pay_in.amount = new_amount
        pay_in.status = PayInStatus.objects.get(name="In Progress")
        pay_in.updated_at = timezone.now()
        pay_in.save(update_fields=["amount", "status", "updated_at"])
        return pay_in

    if uses_melbet_kzt_settlement(solution.merchant, payment_system_obj):
        merchant_fee = merchant_fee_in_kzt(new_amount, solution.mdr_in)
    else:
        merchant_fee = solution.mdr_in * usd_amount / Decimal(100)
    team_rate = TraderTeamRates.objects.get(
        team=chosen_detail.group.trader.team,
        payment_system=payment_system_obj,
    )
    trader_fee = team_rate.mdr_in * usd_amount / Decimal(100)

    order.payment_details = chosen_detail
    order.merchant_fee = merchant_fee
    order.trader_fee = trader_fee
    order.status = InOrderStatus.objects.get(name="New")
    order.save()

    try:
        order.freeze(comment="Melbet amount probe retry")
    except ValidationError:
        order.payment_details = None
        order.status = InOrderStatus.objects.get(name="Cannot process")
        order.save(update_fields=["payment_details", "status"])

    pay_in.amount = new_amount
    pay_in.status = PayInStatus.objects.get(name="In Progress")
    pay_in.updated_at = timezone.now()
    pay_in.save(update_fields=["amount", "status", "updated_at"])
    return pay_in
