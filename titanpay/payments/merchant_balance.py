"""GET /api/v1/payments/balance/ — баланс мерчанта по API-токену."""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from basics.permissions import MerchantPermission


def _money(value) -> str:
    amount = Decimal(value or 0).quantize(Decimal("0.01"))
    return format(amount, "f")


def _deposit_address(balance) -> str:
    if balance is None:
        return ""
    rel = getattr(balance, "address", None)
    if rel is None:
        return ""
    try:
        addr = rel.get()
    except ObjectDoesNotExist:
        return ""
    return (getattr(addr, "address_public", None) or "").strip()


def merchant_balance_payload(merchant) -> dict:
    """Те же поля, что кабинет мерчанта: USDT, холд, адрес пополнения.

    KZT/KGS добавляются только мерчантам с отдельным фиатным ledger (Melbet).
    """
    available = getattr(merchant, "balance", None)
    frozen = getattr(merchant, "frozen_balance", None)
    data = {
        "amount": _money(getattr(available, "amount", None)),
        "frozen_amount": _money(getattr(frozen, "amount", None)),
        "currency": "USDT",
        "deposit_address": _deposit_address(available),
    }

    from merchant.kzt_settlement import is_melbet_merchant

    if is_melbet_merchant(merchant):
        kzt = getattr(merchant, "balance_kzt", None)
        kzt_frozen = getattr(merchant, "frozen_balance_kzt", None)
        kgs = getattr(merchant, "balance_kgs", None)
        kgs_frozen = getattr(merchant, "frozen_balance_kgs", None)
        data["amount_kzt"] = _money(getattr(kzt, "amount", None))
        data["frozen_amount_kzt"] = _money(getattr(kzt_frozen, "amount", None))
        data["currency_kzt"] = "KZT"
        data["amount_kgs"] = _money(getattr(kgs, "amount", None))
        data["frozen_amount_kgs"] = _money(getattr(kgs_frozen, "amount", None))
        data["currency_kgs"] = "KGS"
    return data


def _response_signature(merchant, data) -> str | None:
    keys = getattr(merchant, "api_keys", None)
    if keys is None:
        return None
    try:
        key = keys.filter(active=True).first()
    except Exception:
        return None
    if key is None or not hasattr(key, "sign_data"):
        return None
    return key.sign_data(data)


class MerchantBalanceView(APIView):
    """Баланс текущего мерчанта. Авторизация: Authorization: Token <api_token>."""

    permission_classes = [MerchantPermission | IsAdminUser]

    def get(self, request):
        merchant = getattr(request.user, "merchant", None)
        if merchant is None:
            return Response(
                {"error": "You are not a merchant"},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = merchant_balance_payload(merchant)
        response = Response(data, status=status.HTTP_200_OK)
        signature = _response_signature(merchant, data)
        if signature:
            response["Signature"] = signature
        return response
