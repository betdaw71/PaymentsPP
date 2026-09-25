"""Inbound webhooks from GiPay PSP (gipay.org)."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.gipay_client import (
    gipay_webhook_outcome,
    resolve_gipay_webhook_session,
    verify_webhook_signature,
    webhook_signature_debug_hint,
)
from payments.models import GipayPayInSession, PayIn
from payments.payin_trace import Direction, trace_log
from payments.psp_payin import complete_inorder_from_psp_webhook
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


class GipayWebhookView(APIView):
    """POST /api/v1/webhooks/psp/gipay/ — callback (state: finished / expired / ...)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def _extract_signature(self, request) -> str | None:
        for key in ("Signature", "X-Signature", "x-signature"):
            value = request.headers.get(key)
            if value:
                return value
        for meta_key in ("HTTP_SIGNATURE", "HTTP_X_SIGNATURE"):
            value = request.META.get(meta_key)
            if value:
                return value
        return None

    def post(self, request, *args, **kwargs):
        raw_body = request.body or b""
        signature = self._extract_signature(request)
        if not verify_webhook_signature(raw_body, signature):
            logger.warning(
                "GiPay webhook: invalid signature hint=%s headers=%s",
                webhook_signature_debug_hint(raw_body, signature),
                {
                    "Signature": bool(request.headers.get("Signature") or request.META.get("HTTP_SIGNATURE")),
                    "X-Signature": bool(request.headers.get("X-Signature") or request.META.get("HTTP_X_SIGNATURE")),
                },
            )
            return Response({"ok": False, "error": "invalid_signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            body = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}

        order_id = body.get("orderId")
        payment_id = body.get("id") or body.get("paymentId")
        outcome = gipay_webhook_outcome(body)

        session = resolve_gipay_webhook_session(order_id=order_id, payment_id=payment_id)

        if session is None:
            logger.warning("GiPay webhook: session not found orderId=%s id=%s", order_id, payment_id)
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        trace_log(
            pay_in=session.pay_in,
            direction=Direction.GIPAY_WEBHOOK,
            body=body,
            http_method="POST",
            url="/api/v1/webhooks/psp/gipay/",
            note=f"linked pay_in state={body.get('state')}",
        )

        session.last_webhook_payload = body
        session.last_notified_state = _norm_status(body.get("state")) or session.last_notified_state
        session.save()

        if outcome == "success":
            return self._handle_success(session, body)
        if outcome == "fail":
            return self._handle_terminal_fail(session)
        logger.warning(
            "GiPay webhook ignored PayIn=%s state=%s",
            session.pay_in_id,
            body.get("state"),
        )
        return Response({"ok": True, "ignored": True})

    def _handle_success(self, session: GipayPayInSession, body: dict) -> Response:
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
                "GiPay success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)

        return Response({"ok": True})

    def _handle_terminal_fail(self, session: GipayPayInSession) -> Response:
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
                    logger.exception("GiPay webhook deal_time_expired: %s", exc)
            if (
                not inorder_closed
                and locked_pi.status
                and locked_pi.status.name not in ("Success", "Failed", "Declined")
            ):
                locked_pi.failed()

        return Response({"ok": True})
