"""Inbound webhooks from Astrum PSP (KZT pay-in / pay-out)."""
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

from payments.astrum_client import (
    astrum_payin_webhook_outcome,
    astrum_payout_webhook_outcome,
    astrum_webhook_foreign_id,
    astrum_webhook_inner_id,
)
from payments.models import AstrumPayInSession, AstrumPayOutSession, PayIn, PayOut
from payments.psp_payin import complete_inorder_from_psp_webhook
from trade.models import InOrder, OutOrder, OutOrderStatus

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip()


def _status_from_body(body: dict) -> str:
    if isinstance(body.get("status"), str):
        return body["status"]
    if isinstance(body.get("result"), dict) and isinstance(body["result"].get("status"), str):
        return body["result"]["status"]
    return ""


class AstrumPayoutWebhookView(APIView):
    """POST /api/v1/webhooks/psp/astrum/payout/"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        raw_body = request.body or b""
        try:
            body = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}

        if not isinstance(body, dict):
            return Response({"ok": False, "error": "invalid_body"}, status=status.HTTP_400_BAD_REQUEST)

        foreign_id = astrum_webhook_foreign_id(body)
        inner_id = astrum_webhook_inner_id(body)
        outcome = astrum_payout_webhook_outcome(body)

        session = None
        if foreign_id:
            session = (
                AstrumPayOutSession.objects.filter(external_id=str(foreign_id))
                .select_related("pay_out", "pay_out__order")
                .first()
            )
        if session is None and inner_id:
            session = (
                AstrumPayOutSession.objects.filter(provider_application_id=str(inner_id))
                .select_related("pay_out", "pay_out__order")
                .first()
            )

        if session is None:
            logger.warning(
                "Astrum payout webhook: session not found foreign_id=%s inner_id=%s",
                foreign_id,
                inner_id,
            )
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        status_raw = _status_from_body(body)
        session.last_webhook_payload = body
        session.last_notified_status = _norm_status(status_raw) or session.last_notified_status
        if inner_id and not session.provider_application_id:
            session.provider_application_id = str(inner_id)
        session.save()

        if outcome == "success":
            return self._handle_success(session)
        if outcome == "fail":
            return self._handle_fail(session)
        logger.info(
            "Astrum payout webhook ignored PayOut=%s status=%s",
            session.pay_out_id,
            status_raw,
        )
        return Response({"ok": True, "ignored": True})

    def _handle_success(self, session: AstrumPayOutSession) -> Response:
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

    def _handle_fail(self, session: AstrumPayOutSession) -> Response:
        pay_out = session.pay_out
        if not pay_out or not pay_out.order_id:
            return Response({"ok": True})

        with transaction.atomic():
            locked = OutOrder.objects.select_for_update().get(pk=pay_out.order_id)
            if locked.status and locked.status.name == "Completed":
                return Response({"ok": True, "idempotent": True})
            if locked.status and locked.status.name == "New":
                locked.unfreeze("Astrum payout failed")
                locked.decrease_current_volume()
                locked.status = OutOrderStatus.objects.get(name="Cannot process")
                locked.updated_date = timezone.now()
                locked.save(update_fields=["status", "updated_date"])
            locked_po = PayOut.objects.select_for_update().get(pk=pay_out.pk)
            if locked_po.status and locked_po.status.name not in ("Success", "Failed", "Declined"):
                locked_po.failed()

        return Response({"ok": True})


class AstrumPayinWebhookView(APIView):
    """POST /api/v1/webhooks/psp/astrum/payin/"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        raw_body = request.body or b""
        try:
            body = json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = request.data if isinstance(request.data, dict) else {}

        if not isinstance(body, dict):
            return Response({"ok": False, "error": "invalid_body"}, status=status.HTTP_400_BAD_REQUEST)

        foreign_id = astrum_webhook_foreign_id(body)
        inner_id = astrum_webhook_inner_id(body)
        outcome = astrum_payin_webhook_outcome(body)

        session = None
        if foreign_id:
            session = (
                AstrumPayInSession.objects.filter(external_id=str(foreign_id))
                .select_related("pay_in", "pay_in__order")
                .first()
            )
        if session is None and inner_id:
            session = (
                AstrumPayInSession.objects.filter(provider_deal_id=str(inner_id))
                .select_related("pay_in", "pay_in__order")
                .first()
            )

        if session is None:
            logger.warning(
                "Astrum payin webhook: session not found foreign_id=%s inner_id=%s",
                foreign_id,
                inner_id,
            )
            return Response({"ok": False, "error": "unknown_order"}, status=status.HTTP_404_NOT_FOUND)

        status_raw = _status_from_body(body)
        session.last_webhook_payload = body
        session.last_notified_status = _norm_status(status_raw) or session.last_notified_status
        if inner_id and not session.provider_deal_id:
            session.provider_deal_id = str(inner_id)
        session.save()

        if outcome == "success":
            return self._handle_success(session, body)
        if outcome == "fail":
            return self._handle_fail(session)
        logger.info(
            "Astrum payin webhook ignored PayIn=%s status=%s",
            session.pay_in_id,
            status_raw,
        )
        return Response({"ok": True, "ignored": True})

    def _handle_success(self, session: AstrumPayInSession, body: dict) -> Response:
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
                "Astrum payin success webhook: bad InOrder state %s PayIn=%s detail=%s",
                state,
                pay_in.id,
                exc.detail,
            )
            return Response({"ok": False, "error": "bad_inorder_state"}, status=status.HTTP_409_CONFLICT)

        return Response({"ok": True})

    def _handle_fail(self, session: AstrumPayInSession) -> Response:
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
