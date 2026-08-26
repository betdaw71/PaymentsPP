"""Inbound webhooks from PayPlat PSP (payplat.su IPN)."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import PayIn, PayplatPayInSession
from payments.payin_trace import Direction, trace_log
from payments.payplat_client import (
    payplat_webhook_outcome,
    resolve_payplat_webhook_session,
    verify_webhook_signature,
)
from payments.psp_payin import complete_inorder_from_psp_webhook
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


class PayplatWebhookView(APIView):
    """POST /api/v1/webhooks/psp/payplat/ — IPN (status: SUCCESS / TIMEOUT / ...)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def _header(self, request, name: str) -> str | None:
        value = request.headers.get(name)
        if value:
            return value
        meta_key = "HTTP_" + name.upper().replace("-", "_")
        return request.META.get(meta_key)

    def post(self, request, *args, **kwargs):
        raw_body = request.body or b""
        signature = self._header(request, "X-Signature")
        timestamp = self._header(request, "X-Timestamp")
        authorization = self._header(request, "Authorization")

        if not verify_webhook_signature(
            raw_body,
            signature=signature,
            timestamp=timestamp,
            authorization=authorization,
        ):
            logger.warning("PayPlat webhook: invalid signature shop_internal_id unknown yet")
            return Response({"status": "error", "message": "invalid_signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            body = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}

        shop_internal_id = body.get("shop_internal_id")
        order_id = body.get("order_id")
        outcome = payplat_webhook_outcome(body)

        session = resolve_payplat_webhook_session(
            shop_internal_id=shop_internal_id,
            order_id=order_id,
        )
        if session is None:
            logger.warning(
                "PayPlat webhook: session not found shop_internal_id=%s order_id=%s",
                shop_internal_id,
                order_id,
            )
            return Response({"status": "error", "message": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        trace_log(
            pay_in=session.pay_in,
            direction=Direction.PAYPLAT_WEBHOOK,
            body=body,
            http_method="POST",
            url="/api/v1/webhooks/psp/payplat/",
            note=f"linked pay_in status={body.get('status')}",
        )

        session.last_webhook_payload = body
        session.last_notified_state = _norm_status(body.get("status")) or session.last_notified_state
        if order_id and not session.provider_order_id:
            session.provider_order_id = str(order_id)
        session.save()

        if outcome == "success":
            return self._handle_success(session, body)
        if outcome == "fail":
            return self._handle_terminal_fail(session)
        logger.warning(
            "PayPlat webhook ignored PayIn=%s status=%s",
            session.pay_in_id,
            body.get("status"),
        )
        return Response({"status": "ok", "message": "Webhook received successfully"})

    def _handle_success(self, session: PayplatPayInSession, body: dict) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"status": "error", "message": "no_pay_in"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
                if locked.status and locked.status.name == "Completed":
                    return Response({"status": "ok", "message": "Webhook received successfully"})
                complete_inorder_from_psp_webhook(locked, body)
        except ValidationError as exc:
            state = pay_in.order.status.name if pay_in.order and pay_in.order.status else None
            logger.warning(
                "PayPlat success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"status": "error", "message": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)

        return Response({"status": "ok", "message": "Webhook received successfully"})

    def _handle_terminal_fail(self, session: PayplatPayInSession) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"status": "ok", "message": "Webhook received successfully"})

        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
            if locked.status and locked.status.name == "Completed":
                return Response({"status": "ok", "message": "Webhook received successfully"})
            locked_pi = PayIn.objects.select_for_update().get(pk=pay_in.pk)
            inorder_closed = False
            if locked.status and locked.status.name in ("New", "Money sent by user"):
                try:
                    locked.deal_time_expired()
                    inorder_closed = True
                except Exception as exc:  # noqa: BLE001
                    logger.exception("PayPlat webhook deal_time_expired: %s", exc)
            if (
                not inorder_closed
                and locked_pi.status
                and locked_pi.status.name not in ("Success", "Failed", "Declined")
            ):
                locked_pi.failed()

        return Response({"status": "ok", "message": "Webhook received successfully"})
