"""Inbound webhooks from Protocol PSP (prot0col.com)."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import PayIn, ProtocolPayInSession
from payments.payin_trace import Direction, trace_log
from payments.protocol_client import (
    parse_protocol_webhook_paid_amount,
    protocol_webhook_outcome,
    verify_webhook_signature,
)
from payments.psp_payin import (
    apply_psp_amount_update_from_webhook,
    apply_psp_completed_amount_recalc_from_webhook,
    complete_inorder_from_psp_webhook,
)
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


class ProtocolWebhookView(APIView):
    """POST /api/v1/webhooks/psp/protocol/ — callback из Postman (state: finished / expired / ...)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        raw_body = request.body or b""
        signature = request.headers.get("Signature") or request.META.get("HTTP_SIGNATURE")
        if not verify_webhook_signature(raw_body, signature):
            logger.warning("Protocol webhook: invalid signature")
            return Response({"ok": False, "error": "invalid_signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            body = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}

        order_id = body.get("orderId")
        payment_id = body.get("id") or body.get("paymentId")
        outcome = protocol_webhook_outcome(body)

        session = None
        if order_id:
            session = (
                ProtocolPayInSession.objects.filter(external_id=str(order_id))
                .select_related("pay_in", "pay_in__order")
                .first()
            )
        if session is None and payment_id:
            session = (
                ProtocolPayInSession.objects.filter(provider_payment_id=str(payment_id))
                .select_related("pay_in", "pay_in__order")
                .first()
            )

        if session is None:
            logger.warning("Protocol webhook: session not found orderId=%s id=%s", order_id, payment_id)
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        trace_log(
            pay_in=session.pay_in,
            direction=Direction.PROTOCOL_WEBHOOK,
            body=body,
            http_method="POST",
            url="/api/v1/webhooks/psp/protocol/",
            note=f"linked pay_in state={body.get('state')}",
        )

        session.last_webhook_payload = body
        session.last_notified_state = _norm_status(body.get("state")) or session.last_notified_state
        session.save()

        pay_in = session.pay_in

        if outcome is None and pay_in and pay_in.order_id:
            try:
                with transaction.atomic():
                    locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
                    if locked.status and locked.status.name != "Completed":
                        if apply_psp_amount_update_from_webhook(locked, body):
                            return Response({"ok": True, "amount_updated": True})
            except InOrder.DoesNotExist:
                pass

        if outcome == "success":
            return self._handle_success(session, body)
        if outcome == "fail":
            return self._handle_terminal_fail(session)
        logger.warning(
            "Protocol webhook ignored PayIn=%s state=%s",
            session.pay_in_id,
            body.get("state"),
        )
        return Response({"ok": True, "ignored": True})

    def _handle_success(self, session: ProtocolPayInSession, body: dict) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": False, "error": "no_pay_in"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
                if locked.status and locked.status.name == "Completed":
                    paid_amount = parse_protocol_webhook_paid_amount(body)
                    if paid_amount and apply_psp_completed_amount_recalc_from_webhook(locked, body):
                        return Response({"ok": True, "amount_updated_after_complete": True})
                    return Response({"ok": True, "idempotent": True})
                paid_amount = parse_protocol_webhook_paid_amount(body)
                complete_inorder_from_psp_webhook(locked, body, paid_amount=paid_amount)
        except ValidationError as exc:
            state = pay_in.order.status.name if pay_in.order and pay_in.order.status else None
            logger.warning(
                "Protocol success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)

        return Response({"ok": True})

    def _handle_terminal_fail(self, session: ProtocolPayInSession) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": True})

        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
            if locked.status and locked.status.name == "Completed":
                return Response({"ok": True, "idempotent": True})
            locked_pi = PayIn.objects.select_for_update().get(pk=pay_in.pk)
            if locked_pi.status and locked_pi.status.name not in ("Success", "Failed", "Declined"):
                locked_pi.failed()

        return Response({"ok": True})
