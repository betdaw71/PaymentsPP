"""Inbound webhooks from Syndicate Pay PSP."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import ValidationError

from payments.models import PayIn, SyndicatePayInSession
from payments.payin_trace import Direction, trace_log
from payments.psp_payin import complete_inorder_from_psp_webhook
from payments.syndicate_client import syndicate_webhook_outcome, verify_syndicate_callback_signature
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _json_response(data: dict, *, status: int = 200) -> JsonResponse:
    return JsonResponse(data, status=status)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _handle_success(session: SyndicatePayInSession, body: dict) -> JsonResponse:
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
            "Syndicate success webhook: bad InOrder state %s PayIn=%s detail=%s",
            inorder_state,
            pay_in.id,
            exc.detail,
        )
        return _json_response({"ok": False, "error": "bad_inorder_state"}, status=409)

    return _json_response({"ok": True})


def _handle_terminal_fail(session: SyndicatePayInSession) -> JsonResponse:
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
                logger.exception("Syndicate webhook deal_time_expired: %s", exc)
        if (
            not inorder_closed
            and locked_pi.status
            and locked_pi.status.name not in ("Success", "Failed", "Declined")
        ):
            locked_pi.failed()

    return _json_response({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def syndicate_webhook_view(request):
    """POST /api/v1/webhooks/psp/syndicate/ — callback виджета / H2H."""
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {}

    if not isinstance(body, dict):
        body = {}

    if not verify_syndicate_callback_signature(body):
        logger.warning("Syndicate webhook: invalid signature invid=%s", body.get("InvId") or body.get("invid"))
        return _json_response({"ok": False, "error": "invalid_signature"}, status=403)

    invid = body.get("InvId") or body.get("invid")
    session = None
    if invid:
        session = (
            SyndicatePayInSession.objects.filter(external_id=str(invid))
            .select_related("pay_in", "pay_in__order")
            .first()
        )

    if session is None:
        logger.warning("Syndicate webhook: session not found invid=%s", invid)
        return _json_response({"ok": False, "error": "unknown_order"}, status=404)

    trace_log(
        pay_in=session.pay_in,
        direction=Direction.SYNDICATE_WEBHOOK,
        body=body,
        http_method="POST",
        url="/api/v1/webhooks/psp/syndicate/",
        note=f"linked pay_in status={body.get('Status') or body.get('status')}",
    )

    session.last_webhook_payload = body
    session.last_notified_status = _norm_status(body.get("Status") or body.get("status")) or session.last_notified_status
    session.save()

    outcome = syndicate_webhook_outcome(body)
    if outcome == "success":
        return _handle_success(session, body)
    if outcome == "fail":
        return _handle_terminal_fail(session)
    return _json_response({"ok": True, "ignored": True})
