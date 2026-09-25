"""Inbound webhooks from PayMap PSP (API v2)."""
from __future__ import annotations

import logging

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import PaymapPayInSession, PayIn
from payments.payin_trace import Direction, trace_log
from payments.paymap_client import _invoice_id_from_webhook, paymap_webhook_outcome
from payments.psp_payin import complete_inorder_from_psp_webhook
from trade.models import InOrder

logger = logging.getLogger(__name__)


class PaymapWebhookView(APIView):
    """POST /api/v1/webhooks/psp/paymap/ — callbackUrl from fiat/create."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        customer_request_id = (body.get("customer_request_id") or "").strip()
        invoice_uuid = _invoice_id_from_webhook(body)
        outcome = paymap_webhook_outcome(body)

        session = None
        if customer_request_id:
            session = (
                PaymapPayInSession.objects.filter(external_id=customer_request_id)
                .select_related("pay_in", "pay_in__order")
                .first()
            )
        if session is None and invoice_uuid:
            session = (
                PaymapPayInSession.objects.filter(provider_invoice_id=invoice_uuid)
                .select_related("pay_in", "pay_in__order")
                .first()
            )

        if session is None:
            logger.warning(
                "PayMap webhook: session not found customer_request_id=%s invoice_uuid=%s",
                customer_request_id,
                invoice_uuid,
            )
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        trace_log(
            pay_in=session.pay_in,
            direction=Direction.PAYMAP_WEBHOOK,
            body=body,
            http_method="POST",
            url="/api/v1/webhooks/psp/paymap/",
            note=f"status={body.get('status')}",
        )

        session.last_webhook_payload = body
        session.last_notified_status = str(body.get("status") or "")
        session.save()

        if outcome == "success":
            return self._handle_success(session, body)
        if outcome == "fail":
            return self._handle_terminal_fail(session)
        return Response({"ok": True, "ignored": True})

    def _handle_success(self, session: PaymapPayInSession, body: dict) -> Response:
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
                "PayMap success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)

        return Response({"ok": True})

    def _handle_terminal_fail(self, session: PaymapPayInSession) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": True})

        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
            if locked.status and locked.status.name == "Completed":
                return Response({"ok": True, "idempotent": True})
            if locked.status and locked.status.name == "New":
                try:
                    locked.cancel_order()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("PayMap webhook cancel_order: %s", exc)
            locked_pi = PayIn.objects.select_for_update().get(pk=pay_in.pk)
            if locked_pi.status and locked_pi.status.name not in ("Success", "Failed", "Declined"):
                locked_pi.failed()

        return Response({"ok": True})
