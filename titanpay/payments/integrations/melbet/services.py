from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from basics.models import Currency, PaymentSystem
from merchant.models import MerchantSolution
from payments.integrations.melbet.amount_probe import (
    is_melbet_deposit_allocated,
    melbet_candidate_amounts,
    reallocate_melbet_in_order,
)
from payments.integrations.melbet.mapping import (
    account_number_to_details,
    client_name_from_fields,
    map_internal_status_to_melbet,
    mask_account_number,
    resolve_method_entry,
)
from payments.integrations.melbet.models import MelbetIntegrationConfig, MelbetTransactionSession
from payments.models import PayIn, PayInStatus, PayOut, PayOutStatus
from payments.psp_payin import decline_payin, try_attach_psp_sessions
from payments.utils import generate_link
from payments.utils2 import assert_payin_amount_within_solution, check_pending, get_client_object
from trade.models import InOrder, OutOrder, OutOrderStatus

logger = logging.getLogger(__name__)


class MelbetServiceError(Exception):
    def __init__(self, message: str, *, code: int = 400):
        super().__init__(message)
        self.code = code


def _client_id_from_payload(payload: dict) -> str:
    raw = payload.get("customer_account_id")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    if fields.get("email"):
        return str(fields["email"]).strip()[:255]
    order_id = (payload.get("order_id") or "").strip()
    if order_id:
        return order_id
    raise MelbetServiceError("customer_account_id or order_id required", code=400)


def _client_payload_from_melbet(payload: dict) -> dict:
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    return {
        "client_id": _client_id_from_payload(payload),
        "email": (fields.get("email") or "").strip() or None,
        "phone": (fields.get("phone") or "").strip() or None,
        "name": client_name_from_fields(fields),
    }


def _resolve_ps(config: MelbetIntegrationConfig, payload: dict) -> tuple[Currency, PaymentSystem]:
    currency_symbol = (payload.get("currency") or "").strip().upper()
    if not currency_symbol:
        raise MelbetServiceError("currency is required", code=400)
    try:
        currency = Currency.objects.get(symbol__iexact=currency_symbol)
    except Currency.DoesNotExist as exc:
        raise MelbetServiceError(f"Currency {currency_symbol} is not supported", code=400) from exc
    try:
        entry = resolve_method_entry(
            config,
            currency=currency_symbol,
            method=payload.get("method"),
        )
    except ValueError as exc:
        raise MelbetServiceError(str(exc), code=400) from exc
    payment_system = PaymentSystem.objects.filter(
        name__iexact=entry["payment_system"],
        currency=currency,
    ).first()
    if payment_system is None:
        raise MelbetServiceError(
            f"Payment system {entry['payment_system']} is not available for {currency_symbol}",
            code=400,
        )
    return currency, payment_system


def _assert_no_duplicate_order(config: MelbetIntegrationConfig, order_id: str) -> None:
    if MelbetTransactionSession.objects.filter(config=config, order_id=order_id).exists():
        raise MelbetServiceError("Order with this order_id already exists", code=409)
    if InOrder.objects.filter(solution__merchant=config.merchant, merchant_order_id=order_id).exists():
        raise MelbetServiceError("Order with this order_id already exists", code=409)
    if OutOrder.objects.filter(solution__merchant=config.merchant, merchant_order_id=order_id).exists():
        raise MelbetServiceError("Order with this order_id already exists", code=409)


def _fail_melbet_deposit_allocation(pay_in: PayIn, *, send_callback: bool = False) -> None:
    """API 400, но PayIn/InOrder уже в БД — для панели и payin_trace/diagnose."""
    decline_payin(pay_in, send_callback=send_callback)
    raise MelbetServiceError("Could not allocate payment requisites", code=400)


def create_melbet_deposit(
    config: MelbetIntegrationConfig,
    payload: dict[str, Any],
    *,
    client_ip: str | None = None,
) -> PayIn:
    order_id = (payload.get("order_id") or "").strip()
    if not order_id:
        raise MelbetServiceError("order_id is required", code=400)
    for field in ("amount", "callback_url", "success_url", "pending_url", "fail_url"):
        if not payload.get(field):
            raise MelbetServiceError(f"{field} is required", code=400)

    _assert_no_duplicate_order(config, order_id)

    currency, payment_system = _resolve_ps(config, payload)
    requested_amount = Decimal(str(payload["amount"]))
    merchant = config.merchant
    ftd = config.default_ftd

    solution = MerchantSolution.objects.filter(
        merchant=merchant,
        payment_system=payment_system,
        ftd=ftd,
        status=1,
    ).first()
    if solution is None:
        raise MelbetServiceError("This payment method is not active", code=400)

    try:
        assert_payin_amount_within_solution(solution, requested_amount)
    except ValidationError as exc:
        detail = exc.detail
        message = detail.get("error") if isinstance(detail, dict) else str(detail)
        raise MelbetServiceError(str(message), code=400) from exc

    client, ok = get_client_object(_client_payload_from_melbet(payload), merchant)
    if not ok:
        raise MelbetServiceError("Client is blacklisted", code=400)
    if check_pending(client, _in=True):
        raise MelbetServiceError("Client has a pending pay-in", code=409)

    candidate_amounts = melbet_candidate_amounts(requested_amount, solution)
    first_amount = candidate_amounts[0]

    with transaction.atomic():
        in_order = InOrder.create(
            amount=first_amount,
            solution=solution,
            client_deposit_count=client.order_count,
            merchant_order_id=order_id,
        )
        pay_in = PayIn.objects.create(
            amount=first_amount,
            currency=currency,
            payment_system=payment_system,
            merchant_order_id=order_id,
            success_url=payload.get("success_url"),
            failed_url=payload.get("fail_url"),
            pending_url=payload.get("pending_url"),
            callback_url=payload["callback_url"],
            merchant=merchant,
            order=in_order,
            status=PayInStatus.objects.get(name="In Progress"),
            client=client,
        )

        MelbetTransactionSession.objects.create(
            config=config,
            pay_in=pay_in,
            order_id=order_id,
            melbet_method=(payload.get("method") or "").strip(),
        )

    from payments.payin_trace import Direction, trace_log, trace_routing_result

    for idx, candidate_amount in enumerate(candidate_amounts):
        if idx > 0:
            reallocate_melbet_in_order(pay_in, candidate_amount, solution, client)
            pay_in.refresh_from_db()

        in_order = pay_in.order
        in_order.refresh_from_db()
        trace_routing_result(pay_in, in_order)
        in_order.refresh_from_db()

        if in_order.status.name != "Cannot process":
            try_attach_psp_sessions(pay_in)

        pay_in.refresh_from_db()
        in_order.refresh_from_db()
        if is_melbet_deposit_allocated(pay_in):
            if candidate_amount != requested_amount:
                trace_log(
                    pay_in=pay_in,
                    direction=Direction.ROUTING,
                    body={
                        "amount_probe": True,
                        "requested_amount": str(requested_amount),
                        "allocated_amount": str(candidate_amount),
                        "attempt": idx + 1,
                    },
                    note=f"melbet amount probe {requested_amount} -> {candidate_amount}",
                )
            break
    else:
        _fail_melbet_deposit_allocation(pay_in, send_callback=False)

    _ = client_ip
    return pay_in


def _fail_melbet_withdrawal(pay_out: PayOut) -> None:
    pay_out.declined()
    raise MelbetServiceError("Could not process withdrawal", code=400)


def create_melbet_withdrawal(
    config: MelbetIntegrationConfig,
    payload: dict[str, Any],
    *,
    client_ip: str | None = None,
) -> PayOut:
    order_id = (payload.get("order_id") or "").strip()
    account_number = (payload.get("account_number") or "").strip().replace(" ", "")
    if not order_id:
        raise MelbetServiceError("order_id is required", code=400)
    if not account_number:
        raise MelbetServiceError("account_number is required", code=400)
    if not payload.get("callback_url"):
        raise MelbetServiceError("callback_url is required", code=400)

    _assert_no_duplicate_order(config, order_id)

    currency, payment_system = _resolve_ps(config, payload)
    amount = Decimal(str(payload["amount"]))
    merchant = config.merchant
    ftd = config.default_ftd
    details = account_number_to_details(account_number, payment_system.name)

    solution = MerchantSolution.objects.filter(
        merchant=merchant,
        payment_system=payment_system,
        ftd=ftd,
        status=1,
    ).first()
    if solution is None:
        raise MelbetServiceError("This payment method is not active", code=400)
    if not solution.min_limit_out <= amount <= solution.max_limit_out:
        raise MelbetServiceError("Amount out of limits", code=400)

    client, ok = get_client_object(_client_payload_from_melbet(payload), merchant)
    if not ok:
        raise MelbetServiceError("Client is blacklisted", code=400)
    if check_pending(client, _in=False):
        raise MelbetServiceError("Client has a pending pay-out", code=409)

    with transaction.atomic():
        try:
            out_order = OutOrder.create(
                amount=amount,
                merchant_order_id=order_id,
                details=details,
                solution=solution,
            )
        except ValidationError as exc:
            detail = exc.detail
            if isinstance(detail, dict) and detail.get("details"):
                raise MelbetServiceError(str(detail["details"]), code=400) from exc
            raise MelbetServiceError(str(detail), code=400) from exc

        pay_out = PayOut.objects.create(
            amount=amount,
            currency=currency,
            payment_system=payment_system,
            merchant_order_id=order_id,
            callback_url=payload["callback_url"],
            merchant=merchant,
            order=out_order,
            status=PayOutStatus.objects.get(name="New"),
            details=details,
            client=client,
        )

        MelbetTransactionSession.objects.create(
            config=config,
            pay_out=pay_out,
            order_id=order_id,
            melbet_method=(payload.get("method") or "").strip(),
            account_number=account_number,
        )

    out_order.refresh_from_db()
    if out_order.status.name == "Cannot process":
        _fail_melbet_withdrawal(pay_out)

    from payments.playments_client import try_create_playments_payout

    playments_ok = try_create_playments_payout(pay_out, client_ip=client_ip)
    if playments_ok is False:
        with transaction.atomic():
            od = OutOrder.objects.select_for_update().get(pk=out_order.pk)
            if od.status and od.status.name == "New":
                od.unfreeze("Playments withdrawal create failed")
                od.decrease_current_volume()
                od.status = OutOrderStatus.objects.get(name="Cannot process")
                od.updated_date = timezone.now()
                od.save(update_fields=["status", "updated_date"])
        _fail_melbet_withdrawal(pay_out)

    pay_out.in_progress()
    return pay_out


def deposit_response(pay_in: PayIn) -> dict:
    return {
        "transaction_id": str(pay_in.id),
        "redirect_url": generate_link(pay_in.id, pay_in.payment_system.name),
    }


def withdrawal_response(pay_out: PayOut) -> dict:
    return {"transaction_id": str(pay_out.id)}


def get_session_for_transaction(
    config: MelbetIntegrationConfig,
    transaction_id: str,
) -> MelbetTransactionSession | None:
    return (
        MelbetTransactionSession.objects.select_related(
            "pay_in__status",
            "pay_in__currency",
            "pay_in__payment_system",
            "pay_out__status",
            "pay_out__currency",
            "pay_out__payment_system",
        )
        .filter(config=config)
        .filter(models_q_transaction(transaction_id))
        .first()
    )


def models_q_transaction(transaction_id: str):
    from django.db.models import Q

    return Q(pay_in_id=transaction_id) | Q(pay_out_id=transaction_id)


def status_response(session: MelbetTransactionSession) -> dict:
    if session.pay_in_id:
        pay = session.pay_in
    else:
        pay = session.pay_out

    status_name = pay.status.name if pay.status else None
    melbet_status = map_internal_status_to_melbet(status_name)
    if melbet_status is None:
        raise MelbetServiceError("Transaction not found", code=404)

    body: dict[str, Any] = {
        "order_id": session.order_id,
        "transaction_id": str(pay.id),
        "status": melbet_status,
        "amount": float(pay.amount),
        "currency": pay.currency.symbol if pay.currency else "",
        "method": session.melbet_method or (pay.payment_system.name if pay.payment_system else ""),
    }

    acct = session.account_number
    if not acct and session.pay_out_id and isinstance(pay.details, dict):
        acct = (
            pay.details.get("card_number")
            or pay.details.get("iban")
            or pay.details.get("phone")
            or ""
        )
    if acct:
        body["account_number"] = mask_account_number(acct)

    if melbet_status == "FAILED":
        body["error"] = {"code": 0, "message": status_name or "FAILED"}

    if session.pay_in_id:
        from payments.psp_payin import requisite_for_payin

        req = requisite_for_payin(pay)
        if req and req.get("deposit_number"):
            body["destination_account_number"] = req.get("deposit_number")
        elif req and req.get("card_number"):
            body["destination_account_number"] = mask_account_number(req.get("card_number"))

    return body
