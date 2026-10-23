"""Provider endpoint for PayPlat payout USDT/KZT rate (XE.com)."""
from __future__ import annotations

import hmac
from datetime import datetime, timezone as dt_timezone

from decimal import Decimal

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from basics.models import PaymentSystem
from payments.payoutkzt_rate import (
    fetch_payoutkzt_xe_quote,
    get_payoutkzt_rate,
    payoutkzt_ps_name,
    store_payoutkzt_rate,
)


def _configured_rate_token() -> str:
    return (getattr(settings, "RATE_API_TOKEN", None) or "").strip()


def _request_rate_token(request) -> str:
    header = (request.headers.get("X-Rate-Token") or "").strip()
    if header:
        return header
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(None, 1)[-1].strip()
    token = request.query_params.get("token") or request.GET.get("token") or ""
    return str(token).strip()


def _token_ok(request) -> bool:
    expected = _configured_rate_token()
    if not expected:
        return True
    provided = _request_rate_token(request)
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


def _ps_updated_at(ps: PaymentSystem | None) -> str | None:
    if ps is None:
        return None
    ts = int(ps.last_update or 0)
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=dt_timezone.utc).isoformat().replace("+00:00", "Z")


def _xe_method() -> dict:
    from payments.payoutkzt_rate import payoutkzt_xe_markup

    return {
        "provider": "xe.com",
        "endpoint": "https://www.xe.com/api/protected/midmarket-converter/",
        "markup": str(payoutkzt_xe_markup()),
    }


class PayoutKztRateView(APIView):
    """GET /api/v1/payments/rate/payoutkzt/ — курс XE.com только для выплат PayPlat.

    Query: live=1 — свежий запрос xe.com.
    Auth: RATE_API_TOKEN via X-Rate-Token / Authorization: Bearer / ?token= (optional).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        if not _token_ok(request):
            return Response({"error": "invalid_token"}, status=status.HTTP_403_FORBIDDEN)

        live = str(request.query_params.get("live") or "").strip().lower() in ("1", "true", "yes")
        ps_name = payoutkzt_ps_name()
        ps = PaymentSystem.objects.filter(name__iexact=ps_name, currency__symbol__iexact="KZT").first()
        method = _xe_method()

        if live:
            quote = fetch_payoutkzt_xe_quote()
            if quote is None:
                rate = get_payoutkzt_rate(live=False)
                payload = {
                    "payment_system": ps_name,
                    "pair": "USDT/KZT",
                    "currency": "KZT",
                    "rate": str(rate) if rate is not None else None,
                    "source": "payoutkzt",
                    "updated_at": _ps_updated_at(ps),
                    "method": method,
                    "live_error": "xe_unavailable",
                }
                if rate is None:
                    return Response(payload, status=status.HTTP_503_SERVICE_UNAVAILABLE)
                return Response(payload)
            store_payoutkzt_rate(quote["rate"])
            ps = PaymentSystem.objects.filter(name__iexact=ps_name, currency__symbol__iexact="KZT").first()
            return Response(
                {
                    "payment_system": ps_name,
                    "pair": "USDT/KZT",
                    "currency": "KZT",
                    "rate": str(quote["rate"]),
                    "source": "xe",
                    "updated_at": _ps_updated_at(ps),
                    "method": {
                        **method,
                        "markup": str(quote["markup"]),
                    },
                    "live": {
                        "base": str(quote["base"]),
                        "markup": str(quote["markup"]),
                    },
                }
            )

        rate = get_payoutkzt_rate(live=False)
        if rate is None:
            return Response(
                {"error": "payoutkzt_rate_unavailable", "payment_system": ps_name},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        ps = PaymentSystem.objects.filter(name__iexact=ps_name, currency__symbol__iexact="KZT").first()
        return Response(
            {
                "payment_system": ps_name,
                "pair": "USDT/KZT",
                "currency": "KZT",
                "rate": str(Decimal(str(rate)).quantize(Decimal("0.01"))),
                "source": "xe",
                "updated_at": _ps_updated_at(ps),
                "method": method,
            }
        )
