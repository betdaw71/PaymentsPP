"""Inbound webhooks from Bitzone PSP."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.bitzone_client import bitzone_webhook_outcome, verify_webhook_signature
from payments.models import BitzonePayInSession, PayIn
from payments.payin_trace import Direction, trace_log
from payments.psp_payin import complete_inorder_from_psp_webhook
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


class BitzoneWebhookView(APIView):
    """POST /api/v1/webhooks/psp/bitzone/ — payload как create pay-in, x-signature HMAC-SHA256."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        raw_body = request.body or b""
        signature = request.headers.get("x-signature") or request.META.get("HTTP_X_SIGNATURE")
        if not verify_webhook_signature(raw_body, signature):
            logger.warning("Bitzone webhook: invalid signature")
            return Response({"ok": False, "error": "invalid_signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            body = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}

        provider_id = body.get("id")
        extra = body.get("extra") if isinstance(body.get("extra"), dict) else {}
        external_id = extra.get("externalTransactionId")
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
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

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
            return self._handle_success(session, body)
        if outcome == "fail":
            return self._handle_terminal_fail(session)
        return Response({"ok": True, "ignored": True})

    def _handle_success(self, session: BitzonePayInSession, body: dict) -> Response:
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
                "Bitzone success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)

        return Response({"ok": True})

    def _handle_terminal_fail(self, session: BitzonePayInSession) -> Response:
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
                    logger.exception("Bitzone webhook deal_time_expired: %s", exc)
            if (
                not inorder_closed
                and locked_pi.status
                and locked_pi.status.name not in ("Success", "Failed", "Declined")
            ):
                locked_pi.failed()

        return Response({"ok": True})
