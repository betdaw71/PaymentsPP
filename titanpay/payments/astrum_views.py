"""Inbound webhooks from Astrum PSP (KZT pay-out)."""
from __future__ import annotations

import json
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.astrum_client import (
    astrum_payout_webhook_outcome,
    astrum_webhook_foreign_id,
    astrum_webhook_inner_id,
)
from payments.models import AstrumPayOutSession, PayOut
from trade.models import OutOrder, OutOrderStatus

logger = logging.getLogger(__name__)


def _norm_status(raw: str | None) -> str:
    return (raw or "").strip()


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

        status_raw = ""
        if isinstance(body.get("status"), str):
            status_raw = body["status"]
        elif isinstance(body.get("result"), dict) and isinstance(body["result"].get("status"), str):
            status_raw = body["result"]["status"]

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
