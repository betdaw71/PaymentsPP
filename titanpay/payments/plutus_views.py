"""Inbound webhooks from PlutusPay PSP."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import ValidationError

from payments.models import PlutusPayInSession, PayIn
from payments.payin_trace import Direction, trace_log
from payments.plutus_client import plutus_webhook_outcome
from payments.psp_payin import complete_inorder_from_psp_webhook
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _json_response(data: dict, *, status: int = 200) -> JsonResponse:
    return JsonResponse(data, status=status)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _handle_success(session: PlutusPayInSession, body: dict) -> JsonResponse:
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
            "Plutus success webhook: bad InOrder state %s PayIn=%s detail=%s",
            inorder_state,
            pay_in.id,
            exc.detail,
        )
        return _json_response({"ok": False, "error": "bad_inorder_state"}, status=409)

    return _json_response({"ok": True})


def _handle_terminal_fail(session: PlutusPayInSession) -> JsonResponse:
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
                logger.exception("Plutus webhook deal_time_expired: %s", exc)
        if (
            not inorder_closed
            and locked_pi.status
            and locked_pi.status.name not in ("Success", "Failed", "Declined")
        ):
            locked_pi.failed()

    return _json_response({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def plutus_webhook_view(request):
    """POST /api/v1/webhooks/psp/plutus/ — callback_url из create pay-in."""
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {}

    if not isinstance(body, dict):
        body = {}

    event = (body.get("event") or "").strip().lower()
    if event in ("requisite_deactivated", "capacity_available"):
        logger.info("Plutus service webhook event=%s body=%s", event, body)
        return _json_response({"ok": True, "event": event})

    platform_id = body.get("platform_id")
    session = None
    if platform_id:
        session = (
            PlutusPayInSession.objects.filter(external_id=str(platform_id))
            .select_related("pay_in", "pay_in__order")
            .first()
        )

    if session is None:
        logger.warning("Plutus webhook: session not found platform_id=%s", platform_id)
        return _json_response({"ok": False, "error": "unknown_order"}, status=404)

    outcome = plutus_webhook_outcome(body)
    trace_log(
        pay_in=session.pay_in,
        direction=Direction.PLUTUS_WEBHOOK,
        body=body,
        http_method="POST",
        url="/api/v1/webhooks/psp/plutus/",
        note=f"linked pay_in status={body.get('status')}",
    )

    session.last_webhook_payload = body
    session.last_notified_status = _norm_status(body.get("status")) or session.last_notified_status
    session.save()

    if outcome == "success":
        return _handle_success(session, body)
    if outcome == "fail":
        return _handle_terminal_fail(session)
    return _json_response({"ok": True, "ignored": True})
