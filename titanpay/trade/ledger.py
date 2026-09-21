"""Балансы, движения по которым видит пользователь.

У мерчанта помимо USDT-балансов могут быть KZT-балансы (melbet-расчёты в тенге),
и проводки по ним должны попадать в ЛК и выгрузки наравне с USDT.
"""
from __future__ import annotations


def merchant_balance_ids(merchant) -> list:
    ids = (
        merchant.balance_id,
        merchant.frozen_balance_id,
        merchant.balance_kzt_id,
        merchant.frozen_balance_kzt_id,
    )
    return [balance_id for balance_id in ids if balance_id is not None]


def user_balance_ids(user) -> list:
    """Балансы пользователя; порядок ролей совпадает с выборкой транзакций."""
    if user is None or not getattr(user, "is_authenticated", False):
        return []

    trader = getattr(user, "trader", None)
    if trader is not None:
        return [
            balance_id
            for balance_id in (trader.balance_usdt_id, trader.frozen_balance_usdt_id)
            if balance_id is not None
        ]

    merchant = getattr(user, "merchant", None)
    if merchant is not None:
        return merchant_balance_ids(merchant)

    submerchant = getattr(user, "submerchant", None)
    if submerchant is not None:
        return merchant_balance_ids(submerchant.merchant)

    teamlead = getattr(user, "teamlead", None)
    if teamlead is not None:
        return [
            balance_id
            for balance_id in (teamlead.balance_id, teamlead.frozen_balance_id)
            if balance_id is not None
        ]

    return []


def kzt_balance_ids() -> set:
    """KZT-балансы всех мерчантов: движения по ним номинированы в тенге, а не в USDT."""
    from merchant.models import Merchant

    ids = set()
    for available_id, frozen_id in Merchant.objects.values_list(
        "balance_kzt_id", "frozen_balance_kzt_id"
    ):
        if available_id is not None:
            ids.add(available_id)
        if frozen_id is not None:
            ids.add(frozen_id)
    return ids
