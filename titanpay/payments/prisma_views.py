"""Inbound webhooks from PrismaPay / Spyder (POST /api/v1/webhooks/psp/prisma/)."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import PayIn, PrismaPayInSession
from payments.payin_trace import Direction, trace_log
from payments.prisma_client import (
    prisma_webhook_outcome,
    resolve_prisma_webhook_session,
    verify_prisma_callback,
)
from payments.psp_payin import handle_psp_success_webhook
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().upper()


class PrismaWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        raw = request.body or b""
        if not verify_prisma_callback(raw_body=raw, headers=request.headers):
            logger.warning("Prisma webhook: invalid signature")
            return Response({"ok": False, "error": "invalid_signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}
        if not isinstance(body, dict):
            body = {}

        order_id = body.get("orderId") or body.get("order_id")
        provider_id = body.get("id")
        session = resolve_prisma_webhook_session(
            order_id=str(order_id) if order_id else None,
            provider_id=str(provider_id) if provider_id else None,
        )
        if session is None:
            logger.warning(
                "Prisma webhook: session not found orderId=%s id=%s",
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

        outcome = prisma_webhook_outcome(body)
        trace_log(
            pay_in=session.pay_in,
            direction=Direction.PRISMA_WEBHOOK,
            body=body,
            http_method="POST",
            url="/api/v1/webhooks/psp/prisma/",
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

    def _handle_success(self, session: PrismaPayInSession, body: dict) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": False, "error": "no_pay_in"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
                handle_psp_success_webhook(locked, body)
        except Exception:
            logger.exception("Prisma success webhook failed session=%s", session.id)
            return Response({"ok": False, "error": "complete_failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"ok": True})

    def _handle_terminal_fail(self, session: PrismaPayInSession) -> Response:
        pay_in: PayIn | None = session.pay_in
        if pay_in is None or not pay_in.order_id:
            return Response({"ok": True, "ignored": True})
        try:
            from payments.psp_payin import mark_inorder_cannot_process_from_psp_api

            mark_inorder_cannot_process_from_psp_api(pay_in, provider="prisma")
        except Exception:
            logger.exception("Prisma fail webhook handling failed session=%s", session.id)
        return Response({"ok": True})
