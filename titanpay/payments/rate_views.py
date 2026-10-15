"""Provider endpoint for PayPlat payout USDT/KZT rate (XE.com, PayPlat-compatible JSON)."""
from __future__ import annotations

import hmac
import logging
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
    payoutkzt_xe_markup,
    store_payoutkzt_rate,
)

logger = logging.getLogger(__name__)


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


def _payplat_method() -> dict:
    """Envelope PayPlat already parses (Kaspi book). Rate value itself is XE."""
    rows_raw = getattr(settings, "BYBIT_KZT_ROWS", "15,16")
    if isinstance(rows_raw, (list, tuple)):
        method_rows = [int(x) for x in rows_raw]
    else:
        method_rows = [int(p.strip()) for p in str(rows_raw).split(",") if p.strip()]
    try:
        method_amount = int(getattr(settings, "BYBIT_KZT_AMOUNT", 50000) or 50000)
    except (TypeError, ValueError):
        method_amount = 50000
    return {
        "amount": method_amount,
        "payment": "Kaspi",
        "verified": bool(getattr(settings, "BYBIT_KZT_AUTH_MAKER", True)),
        "rows": method_rows or [15, 16],
        "side": "sell",
        "provider": "xe.com",
        "markup": str(payoutkzt_xe_markup()),
    }


def _payplat_payload(*, rate: Decimal, ps_name: str, ps, prices: list | None = None) -> dict:
    method = _payplat_method()
    body = {
        "payment_system": ps_name,
        "pair": "USDT/KZT",
        "currency": "KZT",
        "rate": str(Decimal(str(rate)).quantize(Decimal("0.01"))),
        "source": "bybit_kaspi",
        "origin": "xe",
        "updated_at": _ps_updated_at(ps),
        "method": method,
    }
    if prices is not None:
        body["live"] = {
            "prices": [str(p) for p in prices],
            "rows": method["rows"],
            "ads_count": len(prices),
        }
        body["rate"] = str(rate)
    return body


class PayoutKztRateView(APIView):
    """GET /api/v1/payments/rate/payoutkzt/ — курс XE, JSON как ждал PayPlat (live.prices).

    Query: live=1 — свежий xe.com.
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
        logger.info(
            "PAYOUTKZT rate GET live=%s ua=%s ip=%s",
            live,
            request.META.get("HTTP_USER_AGENT", "")[:120],
            request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR"),
        )

        if live:
            quote = fetch_payoutkzt_xe_quote()
            if quote is not None:
                store_payoutkzt_rate(quote["rate"])
                ps = PaymentSystem.objects.filter(name__iexact=ps_name, currency__symbol__iexact="KZT").first()
                return Response(
                    _payplat_payload(
                        rate=quote["rate"],
                        ps_name=ps_name,
                        ps=ps,
                        prices=[quote["rate"], quote["rate"]],
                    )
                )
            rate = get_payoutkzt_rate(live=False)
            if rate is None:
                return Response(
                    {"error": "payoutkzt_rate_unavailable", "payment_system": ps_name},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response(
                _payplat_payload(rate=rate, ps_name=ps_name, ps=ps, prices=[rate, rate])
            )

        rate = get_payoutkzt_rate(live=False)
        if rate is None:
            return Response(
                {"error": "payoutkzt_rate_unavailable", "payment_system": ps_name},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        ps = PaymentSystem.objects.filter(name__iexact=ps_name, currency__symbol__iexact="KZT").first()
        return Response(_payplat_payload(rate=rate, ps_name=ps_name, ps=ps))
