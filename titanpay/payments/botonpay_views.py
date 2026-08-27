"""Inbound webhooks from BotonPay PSP."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import ValidationError

from payments.botonpay_client import (
    botonpay_webhook_outcome,
    find_botonpay_session_for_webhook,
    verify_botonpay_webhook_signature,
)
from payments.models import BotonpayPayInSession, PayIn
from payments.payin_trace import Direction, trace_log
from payments.psp_payin import complete_inorder_from_psp_webhook
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _json_response(data: dict, *, status: int = 200) -> JsonResponse:
    return JsonResponse(data, status=status)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _handle_success(session: BotonpayPayInSession, body: dict) -> JsonResponse:
    pay_in = session.pay_in
    if not pay_in or not pay_in.order_id:
        return _json_response({"ok": False, "error": "no_pay_in"}, status=400)

    inorder_state = None
    try:
        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
            inorder_state = locked.status.name if locked.status else None
            if locked.status and locked.status.name == "Completed":
                return _json_response({"ok": True, "idempotent": True})
            complete_inorder_from_psp_webhook(locked, body)
    except ValidationError as exc:
        logger.warning(
            "BotonPay success webhook: bad InOrder state %s PayIn=%s detail=%s",
            inorder_state,
            pay_in.id,
            exc.detail,
        )
        return _json_response({"ok": False, "error": "bad_inorder_state"}, status=409)

    return _json_response({"ok": True})


def _handle_terminal_fail(session: BotonpayPayInSession) -> JsonResponse:
    pay_in = session.pay_in
    if not pay_in or not pay_in.order_id:
        return _json_response({"ok": True})

    with transaction.atomic():
        locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
        if locked.status and locked.status.name == "Completed":
            return _json_response({"ok": True, "idempotent": True})
        locked_pi = PayIn.objects.select_for_update().get(pk=pay_in.pk)
        inorder_closed = False
        if locked.status and locked.status.name in ("New", "Money sent by user"):
            try:
                locked.deal_time_expired()
                inorder_closed = True
            except Exception as exc:  # noqa: BLE001
                logger.exception("BotonPay webhook deal_time_expired: %s", exc)
        if (
            not inorder_closed
            and locked_pi.status
            and locked_pi.status.name not in ("Success", "Failed", "Declined")
        ):
            locked_pi.failed()

    return _json_response({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def botonpay_webhook_view(request):
    """POST /api/v1/webhooks/psp/botonpay/ — X-Signature HMAC-SHA256(raw body)."""
    raw_body = request.body or b""
    signature = request.headers.get("x-signature") or request.META.get("HTTP_X_SIGNATURE")
    webhook_event = request.headers.get("x-webhook-event") or request.META.get("HTTP_X_WEBHOOK_EVENT")

    if not verify_botonpay_webhook_signature(raw_body, signature):
        logger.warning(
            "BotonPay webhook: invalid signature event=%s body_len=%s",
            webhook_event,
            len(raw_body),
        )
        return _json_response({"ok": False, "error": "invalid_signature"}, status=403)

    try:
        body = json.loads(raw_body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {}

    if not isinstance(body, dict):
        body = {}

    session = find_botonpay_session_for_webhook(body)
    if session is None:
        logger.warning(
            "BotonPay webhook: session not found merchant_order_id=%s deal_uuid=%s",
            body.get("merchant_order_id"),
            body.get("deal_uuid"),
        )
        return _json_response({"ok": False, "error": "unknown_order"}, status=404)

    trace_log(
        pay_in=session.pay_in,
        direction=Direction.BOTONPAY_WEBHOOK,
        body=body,
        http_method="POST",
        url="/api/v1/webhooks/psp/botonpay/",
        note=f"event={webhook_event or body.get('event')} status={body.get('status')}",
    )

    session.last_webhook_payload = body
    if not session.provider_deal_uuid:
        for key in ("deal_uuid", "deal_id"):
            raw = body.get(key)
            if raw:
                session.provider_deal_uuid = str(raw)
                break
    session.last_notified_status = _norm_status(body.get("status")) or session.last_notified_status
    status_version = body.get("status_version")
    if status_version is not None:
        try:
            session.last_status_version = int(status_version)
        except (TypeError, ValueError):
            pass
    session.save(
        update_fields=[
            "last_webhook_payload",
            "provider_deal_uuid",
            "last_notified_status",
            "last_status_version",
            "updated_at",
        ]
    )

    outcome = botonpay_webhook_outcome(body, webhook_event=webhook_event)
    if outcome == "success":
        return _handle_success(session, body)
    if outcome == "fail":
        return _handle_terminal_fail(session)
    logger.info(
        "BotonPay webhook ignored event=%s status=%s PayIn=%s",
        webhook_event or body.get("event"),
        body.get("status"),
        session.pay_in_id,
    )
    return _json_response(
        {
            "ok": True,
            "ignored": True,
            "event": webhook_event or body.get("event"),
            "status": body.get("status"),
        }
    )
