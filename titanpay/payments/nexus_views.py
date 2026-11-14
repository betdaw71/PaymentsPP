"""Inbound webhooks from Nexus / Spyder (POST /api/v1/webhooks/psp/nexus/)."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import NexusPayInSession, PayIn
from payments.nexus_client import (
    nexus_webhook_outcome,
    resolve_nexus_webhook_session,
    verify_nexus_callback,
)
from payments.payin_trace import Direction, trace_log
from payments.psp_payin import handle_psp_success_webhook
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().upper()


class NexusWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        raw = request.body or b""
        if not verify_nexus_callback(raw_body=raw, headers=request.headers):
            logger.warning("Nexus webhook: invalid signature")
            return Response({"ok": False, "error": "invalid_signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}
        if not isinstance(body, dict):
            body = {}

        order_id = body.get("orderId") or body.get("order_id")
        provider_id = body.get("id")
        session = resolve_nexus_webhook_session(
            order_id=str(order_id) if order_id else None,
            provider_id=str(provider_id) if provider_id else None,
        )
        if session is None:
            logger.warning(
                "Nexus webhook: session not found orderId=%s id=%s",
                order_id,
                provider_id,
            )
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        callback_id = (
            request.headers.get("X-Callback-Id")
            or request.headers.get("x-callback-id")
            or ""
        ).strip()
        if callback_id and session.last_callback_id == callback_id:
            return Response({"ok": True, "idempotent": True})

        outcome = nexus_webhook_outcome(body)
        trace_log(
            pay_in=session.pay_in,
            direction=Direction.NEXUS_WEBHOOK,
            body=body,
            http_method="POST",
            url="/api/v1/webhooks/psp/nexus/",
            note=f"status={body.get('status')}",
        )
        session.last_webhook_payload = body
        session.last_notified_state = _norm_status(body.get("status")) or session.last_notified_state
        if provider_id and not session.provider_order_id:
            session.provider_order_id = str(provider_id)
        if callback_id:
            session.last_callback_id = callback_id
        session.save()

        if outcome == "success":
            return self._handle_success(session, body)
        if outcome == "fail":
            return self._handle_terminal_fail(session)
        return Response({"ok": True, "ignored": True})

    def _handle_success(self, session: NexusPayInSession, body: dict) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": False, "error": "no_pay_in"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
                outcome_kind = handle_psp_success_webhook(locked, body)
                if outcome_kind == "recalculated":
                    logger.info("Nexus success webhook recalculated PayIn=%s", pay_in.id)
        except ValidationError as exc:
            state = pay_in.order.status.name if pay_in.order and pay_in.order.status else None
            logger.warning(
                "Nexus success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)
        return Response({"ok": True})

    def _handle_terminal_fail(self, session: NexusPayInSession) -> Response:
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
                    logger.exception("Nexus webhook deal_time_expired: %s", exc)
            if (
                not inorder_closed
                and locked_pi.status
                and locked_pi.status.name not in ("Success", "Failed", "Declined")
            ):
                locked_pi.failed()
        return Response({"ok": True})
