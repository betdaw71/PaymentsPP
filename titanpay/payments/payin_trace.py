"""Полный audit-trail pay-in: тела запросов/ответов мерчанта, Protocol, колбеки."""
from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger("payin.trace")


class Direction:
    MERCHANT_REQUEST = "merchant_request"
    MERCHANT_RESPONSE = "merchant_response"
    ROUTING = "routing"
    PROTOCOL_OUT_REQUEST = "protocol_out_request"
    PROTOCOL_OUT_RESPONSE = "protocol_out_response"
    PROTOCOL_WEBHOOK = "protocol_webhook"
    PLAYMENTS_OUT_REQUEST = "playments_out_request"
    PLAYMENTS_OUT_RESPONSE = "playments_out_response"
    PLAYMENTS_WEBHOOK = "playments_webhook"
    CONCORDED_OUT_REQUEST = "concored_out_request"
    CONCORDED_OUT_RESPONSE = "concored_out_response"
    CONCORDED_WEBHOOK = "concored_webhook"
    PAYMAP_OUT_REQUEST = "paymap_out_request"
    PAYMAP_OUT_RESPONSE = "paymap_out_response"
    PAYMAP_WEBHOOK = "paymap_webhook"
    MERCHANT_CALLBACK = "merchant_callback"


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except (TypeError, ValueError):
        return str(value)[:8000]


def trace_log(
    *,
    direction: str,
    body: Any,
    pay_in=None,
    merchant=None,
    merchant_order_id: str | None = None,
    http_method: str = "",
    url: str = "",
    status_code: int | None = None,
    note: str = "",
) -> None:
    """Сохранить событие в БД и вывести в лог приложения (docker compose logs)."""
    from payments.models import PayInTraceLog

    if pay_in is not None:
        merchant_order_id = merchant_order_id or pay_in.merchant_order_id
        if merchant is None and pay_in.merchant_id:
            merchant = pay_in.merchant

    safe_body = _json_safe(body)
    entry = PayInTraceLog.objects.create(
        pay_in=pay_in,
        merchant=merchant,
        merchant_order_id=(merchant_order_id or "")[:255],
        direction=direction,
        http_method=(http_method or "")[:16],
        url=(url or "")[:512],
        status_code=status_code,
        body=safe_body if isinstance(safe_body, (dict, list)) else {"value": safe_body},
        note=(note or "")[:512],
    )

    pay_in_label = str(pay_in.id) if pay_in is not None else "-"
    merchant_label = merchant.user.username if merchant and getattr(merchant, "user", None) else "-"
    body_preview = json.dumps(safe_body, ensure_ascii=False, default=str)
    if len(body_preview) > 4000:
        body_preview = body_preview[:4000] + "…"

    line = (
        f"PAYIN_TRACE id={entry.id} direction={direction} pay_in={pay_in_label} "
        f"merchant={merchant_label} order={merchant_order_id or '-'} "
        f"http={http_method} url={url} status={status_code} note={note} body={body_preview}"
    )
    logger.info(line)

    if getattr(settings, "PAYIN_TRACE_PRINT", False):
        print(line, flush=True)

    return entry


def trace_routing_result(pay_in, in_order, *, note: str = "") -> None:
    body = {
        "in_order_id": str(in_order.id),
        "in_order_status": in_order.status.name if in_order.status else None,
        "payment_details_id": str(in_order.payment_details_id) if in_order.payment_details_id else None,
        "trader": (
            in_order.payment_details.group.trader.user.username
            if in_order.payment_details is not None
            else None
        ),
        "amount": str(in_order.amount),
        "payment_system": (
            in_order.solution.payment_system.name if in_order.solution and in_order.solution.payment_system else None
        ),
    }
    trace_log(
        pay_in=pay_in,
        direction=Direction.ROUTING,
        body=body,
        note=note or "after InOrder.create",
    )


def wrap_merchant_payin_create(viewset, request, *args, **kwargs):
    """Обёртка для create() в PayIn viewsets: логирует request/response мерчанта."""
    from django.db import transaction
    from rest_framework import status
    from rest_framework.exceptions import ValidationError as DRFValidationError
    from rest_framework.response import Response

    from payments.psp_payin import get_payin_decline_payload

    merchant = request.user.merchant
    trace_log(
        merchant=merchant,
        merchant_order_id=str(request.data.get("merchant_order_id") or ""),
        direction=Direction.MERCHANT_REQUEST,
        body=request.data,
        http_method="POST",
        url=request.path,
        note="merchant create pay-in",
    )
    serializer = viewset.get_serializer(data=request.data)
    try:
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            viewset.perform_create(serializer)
    except DRFValidationError as exc:
        trace_log(
            merchant=merchant,
            merchant_order_id=str(request.data.get("merchant_order_id") or ""),
            direction=Direction.MERCHANT_RESPONSE,
            body=exc.detail,
            http_method="POST",
            url=request.path,
            status_code=400,
            note="validation error",
        )
        raise

    pay_in = serializer.instance
    decline_payload = get_payin_decline_payload(pay_in)
    if decline_payload is not None:
        trace_log(
            pay_in=pay_in,
            direction=Direction.MERCHANT_RESPONSE,
            body=decline_payload,
            http_method="POST",
            url=request.path,
            status_code=400,
            note="declined",
        )
        raise DRFValidationError(decline_payload)

    trace_log(
        pay_in=pay_in,
        direction=Direction.MERCHANT_RESPONSE,
        body=serializer.data,
        http_method="POST",
        url=request.path,
        status_code=201,
        note="create ok",
    )
    signature = merchant.api_keys.get(active=True).sign_data(serializer.data)
    headers = {"Signature": signature, "Content-Type": "application/json"}
    return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
