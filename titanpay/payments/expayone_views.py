"""Inbound webhooks from ExpayOne PSP."""
from __future__ import annotations

import logging

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.expayone_client import _norm_webhook_outcome
from payments.models import ExpayonePayInSession, PayIn
from payments.psp_payin import complete_inorder_from_psp_webhook
from rest_framework.exceptions import ValidationError
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


class ExpayoneWebhookView(APIView):
    """POST /api/v1/webhooks/psp/expayone/ — тело как GET /api/h2h/order/{id}."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        order_id = body.get("order_id")
        ext = body.get("external_id")
        outcome = _norm_webhook_outcome(body)

        session = None
        if order_id:
            session = (
                ExpayonePayInSession.objects.filter(provider_order_id=str(order_id))
                .select_related("pay_in", "pay_in__order")
                .first()
            )
        if session is None and ext:
            session = (
                ExpayonePayInSession.objects.filter(external_id=str(ext))
                .select_related("pay_in", "pay_in__order")
                .first()
            )

        if session is None:
            logger.warning("ExpayOne webhook: session not found order_id=%s ext=%s", order_id, ext)
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        session.last_webhook_payload = body
        session.last_notified_status = _norm_status(body.get("status")) or session.last_notified_status
        session.last_notified_sub_status = _norm_status(body.get("sub_status"))
        session.save()

        if outcome == "success":
            return self._handle_success(session)
        if outcome == "fail":
            return self._handle_terminal_fail(session, body)
        logger.warning(
            "ExpayOne webhook ignored PayIn=%s order_id=%s status=%s sub_status=%s",
            session.pay_in_id,
            order_id,
            body.get("status"),
            body.get("sub_status"),
        )
        return Response({"ok": True, "ignored": True})

    def _handle_success(self, session: ExpayonePayInSession) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": False, "error": "no_pay_in"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
                if locked.status and locked.status.name == "Completed":
                    return Response({"ok": True, "idempotent": True})
                complete_inorder_from_psp_webhook(locked, session.last_webhook_payload)
        except ValidationError as exc:
            state = pay_in.order.status.name if pay_in.order and pay_in.order.status else None
            logger.warning(
                "ExpayOne success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)

        return Response({"ok": True})

    def _handle_terminal_fail(self, session: ExpayonePayInSession, body: dict) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": True})
        sub = _norm_status(body.get("sub_status"))

        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
            if locked.status and locked.status.name == "Completed":
                return Response({"ok": True, "idempotent": True})
            if locked.status and locked.status.name == "New":
                try:
                    locked.cancel_order()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("ExpayOne webhook cancel_order: %s", exc)
            locked_pi = PayIn.objects.select_for_update().get(pk=pay_in.pk)
            if locked_pi.status and locked_pi.status.name not in ("Success", "Failed", "Declined"):
                if sub in ("cancelled", "canceled_by_dispute"):
                    locked_pi.declined()
                else:
                    locked_pi.failed()

        return Response({"ok": True})
