"""Создание pay-in с суммой в USD — только для Alemkredit (opt-in флаг)."""
from decimal import Decimal, ROUND_HALF_UP

from rest_framework.exceptions import ValidationError

ALEMKREDIT_USERNAME = "alemkredit"


def merchant_username(merchant) -> str:
    user = getattr(merchant, "user", None)
    return (getattr(user, "username", None) or "").strip()


def is_alemkredit_merchant(merchant) -> bool:
    return merchant_username(merchant).lower() == ALEMKREDIT_USERNAME


def apply_usd_amount_flag(validated_data: dict, merchant):
    """Если amount_in_usd=true — amount считается USD, в заявке хранится фиат (KZT)."""
    amount_in_usd = bool(validated_data.pop("amount_in_usd", False))
    if not amount_in_usd:
        return validated_data["amount"]
    if not is_alemkredit_merchant(merchant):
        raise ValidationError({"amount_in_usd": "This flag is not enabled"})

    payment_system = validated_data.get("payment_system")
    rate = payment_system.get_rate() if payment_system is not None else None
    if rate is None or Decimal(str(rate)) <= 0:
        raise ValidationError({"amount_in_usd": "Exchange rate is unavailable"})

    usd = Decimal(str(validated_data["amount"]))
    if usd <= 0:
        raise ValidationError({"amount": "Must be greater than 0"})

    fiat = (usd * Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    validated_data["amount"] = fiat
    return fiat
