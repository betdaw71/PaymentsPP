"""Inbound webhooks from VisionX Pay PSP (api.visionxpay.club)."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import PayIn, VisionxPayInSession
from payments.payin_trace import Direction, trace_log
from payments.psp_payin import complete_inorder_from_psp_webhook
from payments.visionx_client import (
    resolve_visionx_webhook_session,
    verify_webhook_token,
    visionx_webhook_outcome,
)
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _invoice_payload(body: dict) -> dict:
    invoice = body.get("invoice")
    return invoice if isinstance(invoice, dict) else body


class VisionxWebhookView(APIView):
    """POST /api/v1/webhooks/psp/visionx/ — callback (invoice.status: paid / expired / ...)."""

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

        invoice = _invoice_payload(body)
        internal_id = invoice.get("internalId")
        invoice_id = invoice.get("id")
        deal = invoice.get("deal") if isinstance(invoice.get("deal"), dict) else {}
        deal_id = deal.get("id")

        session = resolve_visionx_webhook_session(
            internal_id=internal_id,
            invoice_id=invoice_id,
            deal_id=deal_id,
        )
        if session is None:
            logger.warning(
                "VisionX webhook: session not found internalId=%s id=%s",
                internal_id,
                invoice_id,
            )
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        token = self._extract_notification_token(request)
        if not verify_webhook_token(token, session.notification_token):
            logger.warning(
                "VisionX webhook: invalid notification token PayIn=%s",
                session.pay_in_id,
            )
            return Response({"ok": False, "error": "invalid_token"}, status=status.HTTP_403_FORBIDDEN)

        outcome = visionx_webhook_outcome(body)

        trace_log(
            pay_in=session.pay_in,
            direction=Direction.VISIONX_WEBHOOK,
            body=body,
            http_method="POST",
            url="/api/v1/webhooks/psp/visionx/",
            note=f"linked pay_in status={invoice.get('status')}",
        )

        session.last_webhook_payload = body
        session.last_notified_state = _norm_status(invoice.get("status")) or session.last_notified_state
        if invoice_id and not session.provider_invoice_id:
            session.provider_invoice_id = str(invoice_id)
        if deal_id and not session.provider_deal_id:
            session.provider_deal_id = str(deal_id)
        session.save()

        if outcome == "success":
            return self._handle_success(session, body)
        if outcome == "fail":
            return self._handle_terminal_fail(session)
        logger.warning(
            "VisionX webhook ignored PayIn=%s status=%s",
            session.pay_in_id,
            invoice.get("status"),
        )
        return Response({"ok": True, "ignored": True})

    def _handle_success(self, session: VisionxPayInSession, body: dict) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": False, "error": "no_pay_in"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
                if locked.status and locked.status.name == "Completed":
                    return Response({"ok": True, "idempotent": True})
                complete_inorder_from_psp_webhook(locked, body)
        except ValidationError as exc:
            state = pay_in.order.status.name if pay_in.order and pay_in.order.status else None
            logger.warning(
                "VisionX success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)

        return Response({"ok": True})

    def _handle_terminal_fail(self, session: VisionxPayInSession) -> Response:
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
                    logger.exception("VisionX webhook deal_time_expired: %s", exc)
            if (
                not inorder_closed
                and locked_pi.status
                and locked_pi.status.name not in ("Success", "Failed", "Declined")
            ):
                locked_pi.failed()

        return Response({"ok": True})
