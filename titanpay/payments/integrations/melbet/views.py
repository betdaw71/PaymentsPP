from __future__ import annotations

import json

from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.integrations.melbet.auth import MelbetIntegrationAuthentication
from payments.integrations.melbet.services import (
    MelbetServiceError,
    create_melbet_deposit,
    create_melbet_withdrawal,
    deposit_response,
    get_session_for_transaction,
    status_response,
    withdrawal_response,
)
from trade.utils import get_client_ip


def _error_response(message: str, code: int) -> Response:
    http_status = code if 400 <= code < 600 else status.HTTP_400_BAD_REQUEST
    return Response({"error": {"code": code, "message": message}}, status=http_status)


class MelbetAPIView(APIView):
    authentication_classes = [MelbetIntegrationAuthentication]
    permission_classes = []

    def handle_exception(self, exc):
        if isinstance(exc, AuthenticationFailed):
            return _error_response(str(exc.detail if hasattr(exc, "detail") else exc), 401)
        if isinstance(exc, ParseError):
            return _error_response("Bad request", 400)
        return super().handle_exception(exc)

    @property
    def melbet_config(self):
        return getattr(self.request, "melbet_config", None)

    def _parse_json_body(self) -> dict:
        if not self.request.body:
            return {}
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ParseError("Invalid JSON body") from exc
        if not isinstance(data, dict):
            raise ParseError("JSON body must be an object")
        return data


class MelbetDepositView(MelbetAPIView):
    """POST — create deposit (RedirectURL), Melbet spec v2.2."""

    def post(self, request):
        payload = self._parse_json_body()
        try:
            pay_in = create_melbet_deposit(
                self.melbet_config,
                payload,
                client_ip=get_client_ip(request),
            )
        except MelbetServiceError as exc:
            return _error_response(str(exc), exc.code)
        return Response(deposit_response(pay_in), status=status.HTTP_200_OK)


class MelbetWithdrawalView(MelbetAPIView):
    """POST — create withdrawal (host-to-host)."""

    def post(self, request):
        payload = self._parse_json_body()
        try:
            pay_out = create_melbet_withdrawal(
                self.melbet_config,
                payload,
                client_ip=get_client_ip(request),
            )
        except MelbetServiceError as exc:
            return _error_response(str(exc), exc.code)
        return Response(withdrawal_response(pay_out), status=status.HTTP_200_OK)


class MelbetTransactionStatusView(MelbetAPIView):
    """GET — transaction status by PSP transaction_id (PayIn/PayOut UUID)."""

    def get(self, request, transaction_id):
        session = get_session_for_transaction(self.melbet_config, str(transaction_id))
        if session is None:
            return _error_response("Not found", 404)
        try:
            body = status_response(session)
        except MelbetServiceError as exc:
            return _error_response(str(exc), exc.code)
        return Response(body, status=status.HTTP_200_OK)
