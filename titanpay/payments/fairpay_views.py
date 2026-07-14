"""Inbound webhooks from FairPay PSP."""
from __future__ import annotations

import logging

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import FairpayPayInSession, PayIn
from payments.psp_payin import complete_inorder_from_psp_webhook
from rest_framework.exceptions import ValidationError
from trade.models import InOrder

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip().lower()


class FairpayWebhookView(APIView):
    """POST /api/v1/webhooks/psp/fairpay/ — body shape may vary; we match by id or external_id."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        ext = body.get("external_id")
        pid = body.get("id")
        st = _norm_status(body.get("status"))

        session = None
        if pid is not None:
            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                pid_int = None
            if pid_int is not None:
                session = FairpayPayInSession.objects.filter(provider_order_id=pid_int).select_related("pay_in", "pay_in__order").first()
        if session is None and ext:
            session = FairpayPayInSession.objects.filter(external_id=str(ext)).select_related("pay_in", "pay_in__order").first()

        if session is None:
            logger.warning("FairPay webhook: session not found pid=%s ext=%s", pid, ext)
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        session.last_webhook_payload = body
        session.last_notified_status = st or session.last_notified_status
        session.save()

        if st == "success":
            return self._handle_success(session)
        if st in ("failed", "cancelled", "canceled", "expired", "declined"):
            return self._handle_terminal_fail(session, st)
        return Response({"ok": True, "ignored_status": st or None})

    def _handle_success(self, session: FairpayPayInSession) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": False, "error": "no_pay_in"}, status=status.HTTP_400_BAD_REQUEST)
        in_order = pay_in.order

        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=in_order.pk)
                if locked.status and locked.status.name == "Completed":
                    return Response({"ok": True, "idempotent": True})
                complete_inorder_from_psp_webhook(locked, session.last_webhook_payload)
        except ValidationError as exc:
            state = pay_in.order.status.name if pay_in.order and pay_in.order.status else None
            logger.warning(
                "FairPay success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)

        return Response({"ok": True})

    def _handle_terminal_fail(self, session: FairpayPayInSession, st: str) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": True})
        in_order = pay_in.order

        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=in_order.pk)
            if locked.status and locked.status.name == "Completed":
                return Response({"ok": True, "idempotent": True})
            if locked.status and locked.status.name == "New":
                try:
                    locked.cancel_order()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("FairPay webhook cancel_order: %s", exc)
            locked_pi = PayIn.objects.select_for_update().get(pk=pay_in.pk)
            if locked_pi.status and locked_pi.status.name not in ("Success", "Failed", "Declined"):
                if st in ("cancelled", "canceled", "declined"):
                    locked_pi.declined()
                else:
                    locked_pi.failed()

        return Response({"ok": True})
