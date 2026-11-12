"""Inbound webhooks from Bitzone PSP."""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import ValidationError

from payments.bitzone_client import (
    bitzone_webhook_outcome,
    verify_webhook_signature,
    webhook_signature_debug_hint,
    _api_key,
    _signing_keys_for_webhook,
)
from payments.models import BitzonePayInSession, PayIn
from payments.payin_trace import Direction, trace_log
from payments.psp_payin import handle_psp_success_webhook
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _json_response(data: dict, *, status: int = 200) -> JsonResponse:
    return JsonResponse(data, status=status)


def _handle_success(session: BitzonePayInSession, body: dict) -> JsonResponse:
    pay_in = session.pay_in
    if not pay_in or not pay_in.order_id:
        return _json_response({"ok": False, "error": "no_pay_in"}, status=400)

    try:
        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
            outcome_kind = handle_psp_success_webhook(locked, body)
            if outcome_kind == "idempotent":
                return _json_response({"ok": True, "idempotent": True})
            if outcome_kind == "recalculated":
                return _json_response({"ok": True, "recalculated": True})
    except ValidationError as exc:
        state = pay_in.order.status.name if pay_in.order and pay_in.order.status else None
        logger.warning(
            "Bitzone success webhook: bad InOrder state %s PayIn=%s detail=%s",
            state,
            pay_in.id,
            exc.detail,
        )
        return _json_response({"ok": False, "error": "bad_inorder_state"}, status=409)

    return _json_response({"ok": True})


def _handle_terminal_fail(session: BitzonePayInSession) -> JsonResponse:
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
                logger.exception("Bitzone webhook deal_time_expired: %s", exc)
        if (
            not inorder_closed
            and locked_pi.status
            and locked_pi.status.name not in ("Success", "Failed", "Declined")
        ):
            locked_pi.failed()

    return _json_response({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def bitzone_webhook_view(request):
    """POST /api/v1/webhooks/psp/bitzone/ — x-signature HMAC-SHA256 (см. Bitzone Authentication)."""
    raw_body = request.body or b""
    signature = request.headers.get("x-signature") or request.META.get("HTTP_X_SIGNATURE")

    if not verify_webhook_signature(raw_body, signature):
        hint = webhook_signature_debug_hint(raw_body, signature)
        logger.warning(
            "Bitzone webhook: invalid signature api_key_set=%s signing_keys=%s "
            "sig_header=%s sig_len=%s body_len=%s encoding=%s hint=%s",
            bool(_api_key()),
            len(_signing_keys_for_webhook()),
            bool(signature and str(signature).strip()),
            len((signature or "").strip()),
            len(raw_body),
            request.META.get("HTTP_CONTENT_ENCODING", ""),
            hint,
        )
        return _json_response({"ok": False, "error": "invalid_signature"}, status=403)

    try:
        body = json.loads(raw_body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {}

    provider_id = body.get("id")
    extra = body.get("extra") if isinstance(body.get("extra"), dict) else {}
    external_id = body.get("externalTransactionId") or extra.get("externalTransactionId")
    outcome = bitzone_webhook_outcome(body)

    session = None
    if external_id:
        session = (
            BitzonePayInSession.objects.filter(external_id=str(external_id))
            .select_related("pay_in", "pay_in__order")
            .first()
        )
    if session is None and provider_id:
        session = (
            BitzonePayInSession.objects.filter(provider_transaction_id=str(provider_id))
            .select_related("pay_in", "pay_in__order")
            .first()
        )

    if session is None:
        logger.warning("Bitzone webhook: session not found id=%s external=%s", provider_id, external_id)
        return _json_response({"ok": False, "error": "unknown_order"}, status=404)

    trace_log(
        pay_in=session.pay_in,
        direction=Direction.BITZONE_WEBHOOK,
        body=body,
        http_method="POST",
        url="/api/v1/webhooks/psp/bitzone/",
        note=f"linked pay_in status={body.get('status')}",
    )

    session.last_webhook_payload = body
    session.last_notified_status = _norm_status(body.get("status")) or session.last_notified_status
    session.save()

    if outcome == "success":
        return _handle_success(session, body)
    if outcome == "fail":
        return _handle_terminal_fail(session)
    logger.info(
        "Bitzone webhook ignored status=%s external=%s provider_id=%s",
        body.get("status"),
        external_id,
        provider_id,
    )
    return _json_response({"ok": True, "ignored": True, "status": body.get("status")})


# DRF alias (legacy imports)
class BitzoneWebhookView:
    """Deprecated: use bitzone_webhook_view."""

    @classmethod
    def as_view(cls, **initkwargs):
        return bitzone_webhook_view
