"""Inbound webhooks from Playments PSP (TRY bank transfer)."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import PayIn, PayOut, PlaymentsPayInSession, PlaymentsPayOutSession
from payments.payin_trace import Direction, trace_log
from payments.playments_client import (
    playments_deposit_webhook_outcome,
    playments_webhook_payload,
    playments_withdrawal_webhook_outcome,
    verify_webhook_signature,
)
from payments.psp_payin import complete_inorder_from_psp_webhook
from trade.models import InOrder, OutOrder, OutOrderStatus

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip()


class _PlaymentsWebhookBase(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    webhook_path: str = ""

    def _handle_deposit(self, body: dict) -> Response:
        payload = playments_webhook_payload(body)
        merchant_tx = payload.get("merchantTransactionId")
        deposit_id = payload.get("depositId")
        outcome = playments_deposit_webhook_outcome(body)

        session = None
        if merchant_tx:
            session = (
                PlaymentsPayInSession.objects.filter(external_id=str(merchant_tx))
                .select_related("pay_in", "pay_in__order")
                .first()
            )
        if session is None and deposit_id:
            session = (
                PlaymentsPayInSession.objects.filter(provider_deposit_id=str(deposit_id))
                .select_related("pay_in", "pay_in__order")
                .first()
            )

        if session is None:
            logger.warning(
                "Playments deposit webhook: session not found merchantTransactionId=%s depositId=%s",
                merchant_tx,
                deposit_id,
            )
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        trace_log(
            pay_in=session.pay_in,
            direction=Direction.PLAYMENTS_WEBHOOK,
            body=body,
            http_method="POST",
            url=self.webhook_path,
            note=f"deposit status={payload.get('status')}",
        )

        session.last_webhook_payload = body
        session.last_notified_status = _norm_status(payload.get("status")) or session.last_notified_status
        session.save()

        if outcome == "success":
            return self._handle_deposit_success(session, payload)
        if outcome == "fail":
            return self._handle_deposit_fail(session)
        logger.warning(
            "Playments deposit webhook ignored PayIn=%s status=%s",
            session.pay_in_id,
            payload.get("status"),
        )
        return Response({"ok": True, "ignored": True})

    def _handle_deposit_success(self, session: PlaymentsPayInSession, payload: dict) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": False, "error": "no_pay_in"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
                if locked.status and locked.status.name == "Completed":
                    return Response({"ok": True, "idempotent": True})
                complete_inorder_from_psp_webhook(locked, payload)
        except ValidationError as exc:
            state = pay_in.order.status.name if pay_in.order and pay_in.order.status else None
            logger.warning(
                "Playments deposit success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)

        return Response({"ok": True})

    def _handle_deposit_fail(self, session: PlaymentsPayInSession) -> Response:
        pay_in = session.pay_in
        if not pay_in or not pay_in.order_id:
            return Response({"ok": True})

        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=pay_in.order_id)
            if locked.status and locked.status.name == "Completed":
                return Response({"ok": True, "idempotent": True})
            locked_pi = PayIn.objects.select_for_update().get(pk=pay_in.pk)
            if locked_pi.status and locked_pi.status.name not in ("Success", "Failed", "Declined"):
                locked_pi.failed()

        return Response({"ok": True})

    def _handle_withdrawal(self, body: dict) -> Response:
        payload = playments_webhook_payload(body)
        merchant_tx = payload.get("merchantTransactionId")
        withdrawal_id = payload.get("withdrawalId")
        outcome = playments_withdrawal_webhook_outcome(body)

        session = None
        if merchant_tx:
            session = (
                PlaymentsPayOutSession.objects.filter(external_id=str(merchant_tx))
                .select_related("pay_out", "pay_out__order")
                .first()
            )
        if session is None and withdrawal_id:
            session = (
                PlaymentsPayOutSession.objects.filter(provider_withdrawal_id=str(withdrawal_id))
                .select_related("pay_out", "pay_out__order")
                .first()
            )

        if session is None:
            logger.warning(
                "Playments withdrawal webhook: session not found merchantTransactionId=%s withdrawalId=%s",
                merchant_tx,
                withdrawal_id,
            )
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        session.last_webhook_payload = body
        session.last_notified_status = _norm_status(payload.get("status")) or session.last_notified_status
        session.save()

        if outcome == "success":
            return self._handle_withdrawal_success(session)
        if outcome == "fail":
            return self._handle_withdrawal_fail(session)
        logger.warning(
            "Playments withdrawal webhook ignored PayOut=%s status=%s",
            session.pay_out_id,
            payload.get("status"),
        )
        return Response({"ok": True, "ignored": True})

    def _handle_withdrawal_success(self, session: PlaymentsPayOutSession) -> Response:
        pay_out = session.pay_out
        if not pay_out or not pay_out.order_id:
            return Response({"ok": False, "error": "no_pay_out"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            locked = OutOrder.objects.select_for_update().get(pk=pay_out.order_id)
            if locked.status and locked.status.name == "Completed":
                locked_po = PayOut.objects.select_for_update().get(pk=pay_out.pk)
                if locked_po.status and locked_po.status.name != "Success":
                    locked_po.success()
                return Response({"ok": True, "idempotent": True})
            if locked.status and locked.status.name == "New":
                locked.complete()
            locked_po = PayOut.objects.select_for_update().get(pk=pay_out.pk)
            if locked_po.status and locked_po.status.name not in ("Success", "Failed", "Declined"):
                locked_po.success()

        return Response({"ok": True})

    def _handle_withdrawal_fail(self, session: PlaymentsPayOutSession) -> Response:
        pay_out = session.pay_out
        if not pay_out or not pay_out.order_id:
            return Response({"ok": True})

        with transaction.atomic():
            locked = OutOrder.objects.select_for_update().get(pk=pay_out.order_id)
            if locked.status and locked.status.name == "Completed":
                return Response({"ok": True, "idempotent": True})
            if locked.status and locked.status.name == "New":
                locked.unfreeze("Playments withdrawal failed")
                locked.decrease_current_volume()
                locked.status = OutOrderStatus.objects.get(name="Cannot process")
                locked.updated_date = timezone.now()
                locked.save(update_fields=["status", "updated_date"])
            locked_po = PayOut.objects.select_for_update().get(pk=pay_out.pk)
            if locked_po.status and locked_po.status.name not in ("Success", "Failed", "Declined"):
                locked_po.failed()

        return Response({"ok": True})


class PlaymentsDepositWebhookView(_PlaymentsWebhookBase):
    """POST /api/v1/webhooks/psp/playments/deposit/"""

    webhook_path = "/api/v1/webhooks/psp/playments/deposit/"

    def post(self, request, *args, **kwargs):
        raw_body = request.body or b""
        signature = request.headers.get("Request-Signature") or request.META.get("HTTP_REQUEST_SIGNATURE")
        if not verify_webhook_signature(raw_body, signature):
            logger.warning("Playments deposit webhook: invalid signature")
            return Response({"ok": False, "error": "invalid_signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            body = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}

        return self._handle_deposit(body)


class PlaymentsWithdrawalWebhookView(_PlaymentsWebhookBase):
    """POST /api/v1/webhooks/psp/playments/withdrawal/"""

    webhook_path = "/api/v1/webhooks/psp/playments/withdrawal/"

    def post(self, request, *args, **kwargs):
        raw_body = request.body or b""
        signature = request.headers.get("Request-Signature") or request.META.get("HTTP_REQUEST_SIGNATURE")
        if not verify_webhook_signature(raw_body, signature):
            logger.warning("Playments withdrawal webhook: invalid signature")
            return Response({"ok": False, "error": "invalid_signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            body = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}

        return self._handle_withdrawal(body)
