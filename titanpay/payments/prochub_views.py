"""Inbound webhooks from Prochub PSP (prochub.pro)."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import PayIn, ProchubPayInSession
from payments.payin_trace import Direction, trace_log
from payments.prochub_client import (
    prochub_webhook_outcome,
    resolve_prochub_webhook_session,
    verify_webhook_token,
)
from payments.psp_payin import handle_psp_success_webhook
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().upper()


class ProchubWebhookView(APIView):
    """POST /api/v1/webhooks/psp/prochub/ — X-Notification-Token = callbackKey."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def _extract_notification_token(self, request) -> str | None:
        for key in ("X-Notification-Token", "x-notification-token"):
            value = request.headers.get(key)
            if value:
                return value
        return request.META.get("HTTP_X_NOTIFICATION_TOKEN")

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads((request.body or b"").decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}

        internal_id = (
            body.get("internalRequestId")
            or body.get("internalInvoideId")
            or body.get("internalInvoiceId")
        )
        invoice_id = body.get("invoiceId")
        session = resolve_prochub_webhook_session(
            internal_id=str(internal_id) if internal_id else None,
            invoice_id=str(invoice_id) if invoice_id else None,
        )
        if session is None:
            logger.warning(
                "Prochub webhook: session not found internalId=%s invoiceId=%s",
                internal_id,
                invoice_id,
            )
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        token = self._extract_notification_token(request)
        if not verify_webhook_token(token, session.notification_token):
            logger.warning("Prochub webhook: invalid notification token PayIn=%s", session.pay_in_id)
            return Response({"ok": False, "error": "invalid_token"}, status=status.HTTP_403_FORBIDDEN)

        outcome = prochub_webhook_outcome(body)
        trace_log(
            pay_in=session.pay_in,
            direction=Direction.PROCHUB_WEBHOOK,
            body=body,
            http_method="POST",
            url="/api/v1/webhooks/psp/prochub/",
            note=f"status={body.get('status')}",
        )
        session.last_webhook_payload = body
        session.last_notified_state = _norm_status(body.get("status")) or session.last_notified_state
        if invoice_id and not session.provider_invoice_id:
            session.provider_invoice_id = str(invoice_id)
        session.save()

        if outcome == "success":
            return self._handle_success(session, body)
        if outcome == "fail":
            return self._handle_terminal_fail(session)
        return Response({"ok": True, "ignored": True})

    def _handle_success(self, session: ProchubPayInSession, body: dict) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": False, "error": "no_pay_in"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
                outcome_kind = handle_psp_success_webhook(locked, body)
                if outcome_kind == "recalculated":
                    logger.info("Prochub success webhook recalculated PayIn=%s", pay_in.id)
        except ValidationError as exc:
            state = pay_in.order.status.name if pay_in.order and pay_in.order.status else None
            logger.warning(
                "Prochub success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)
        return Response({"ok": True})

    def _handle_terminal_fail(self, session: ProchubPayInSession) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": True})
        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
            if locked.status and locked.status.name == "Completed":
                return Response({"ok": True, "idempotent": True})
            locked_pi = PayIn.objects.select_for_update().get(pk=pay_in.pk)
            inorder_closed = False
            if locked.status and locked.status.name in ("New", "Money sent by user"):
                try:
                    locked.deal_time_expired()
                    inorder_closed = True
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Prochub webhook deal_time_expired: %s", exc)
            if (
                not inorder_closed
                and locked_pi.status
                and locked_pi.status.name not in ("Success", "Failed", "Declined")
            ):
                locked_pi.failed()
        return Response({"ok": True})
