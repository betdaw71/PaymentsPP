"""Melbet merchant settlement in KZT (C2CKZT) — separate from USDT merchant.balance."""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from basics.models import Balance, Currency, PaymentSystem
from django.conf import settings

from merchant.models import Merchant

MELBET_USERNAME = "melbet"
MELBET_TEST_USERNAME = "melbet_test"
KZT_PS_NAME = "C2CKZT"


def melbet_kzt_usernames() -> frozenset[str]:
    raw = getattr(settings, "MELBET_KZT_USERNAMES", MELBET_USERNAME)
    return frozenset(part.strip() for part in str(raw).split(",") if part.strip())


def is_melbet_merchant(merchant: Merchant | None) -> bool:
    if merchant is None or not getattr(merchant, "user", None):
        return False
    return merchant.user.username in melbet_kzt_usernames()


def uses_melbet_kzt_settlement(merchant: Merchant, payment_system) -> bool:
    if not is_melbet_merchant(merchant) or payment_system is None:
        return False
    return (payment_system.name or "").upper() == KZT_PS_NAME


def balance_allows_negative_ledger(balance: Balance) -> bool:
    if balance is None:
        return False
    return Merchant.objects.filter(balance_kzt_id=balance.id).exists() or Merchant.objects.filter(
        frozen_balance_kzt_id=balance.id
    ).exists()


@transaction.atomic
def ensure_kzt_balances(merchant: Merchant) -> Merchant:
    merchant = Merchant.objects.select_for_update().get(pk=merchant.pk)
    if merchant.balance_kzt_id is None:
        merchant.balance_kzt = Balance.objects.create(type=0, amount=Decimal("0"))
    if merchant.frozen_balance_kzt_id is None:
        merchant.frozen_balance_kzt = Balance.objects.create(type=1, amount=Decimal("0"))
    merchant.save(update_fields=["balance_kzt", "frozen_balance_kzt"])
    return merchant


def merchant_available_balance(merchant: Merchant) -> Balance:
    ensure_kzt_balances(merchant)
    merchant.refresh_from_db()
    return merchant.balance_kzt


def merchant_frozen_balance(merchant: Merchant) -> Balance:
    ensure_kzt_balances(merchant)
    merchant.refresh_from_db()
    return merchant.frozen_balance_kzt


def merchant_fee_in_kzt(amount: Decimal, mdr_in: Decimal) -> Decimal:
    return (mdr_in * amount / Decimal(100)).quantize(Decimal("0.01"))


def in_order_credit_kzt(in_order) -> Decimal:
    return (in_order.amount - in_order.merchant_fee).quantize(Decimal("0.01"))


def out_order_freeze_kzt(out_order) -> Decimal:
    return (out_order.amount + out_order.merchant_fee).quantize(Decimal("0.01"))


def c2ckzt_payment_system() -> PaymentSystem | None:
    return PaymentSystem.objects.filter(
        name__iexact=KZT_PS_NAME,
        currency__symbol__iexact="KZT",
    ).first()


def credit_melbet_crypto_deposit(merchant: Merchant, usdt_amount: Decimal) -> bool:
    """USDT detected on chain → credit melbet balance_kzt at C2CKZT rate."""
    from trade.models import Transaction, TransactionType

    ps = c2ckzt_payment_system()
    if ps is None:
        raise ValueError("C2CKZT payment system not found")
    rate = ps.get_rate()
    if not rate or rate <= 0:
        raise ValueError("C2CKZT rate is not configured")
    kzt_amount = (Decimal(str(usdt_amount)) * Decimal(str(rate))).quantize(Decimal("0.01"))
    ensure_kzt_balances(merchant)
    merchant.refresh_from_db()
    blockchain = Balance.objects.get(type=3)
    tx_type = TransactionType.objects.get(name="Deposit")
    Transaction.create(
        blockchain,
        merchant.balance_kzt,
        _transaction_type=tx_type,
        value=kzt_amount,
        _comment=f"Crypto deposit (KZT @ C2CKZT rate {rate})",
    )
    return True


def debit_melbet_crypto_prepaid(
    merchant: Merchant,
    *,
    usdt_amount: Decimal,
    rate: Decimal,
    comment: str | None = None,
):
    """Melbet prepaid USDT → debit balance_kzt (further into minus) at the agreed KZT rate.

    Do not use credit_melbet_crypto_deposit for prepaid: that credits ₸.
    """
    from trade.models import Transaction, TransactionType

    usdt = Decimal(str(usdt_amount))
    rate_d = Decimal(str(rate))
    kzt_amount = (usdt * rate_d).quantize(Decimal("0.01"))
    if usdt <= 0 or rate_d <= 0 or kzt_amount <= 0:
        raise ValueError(f"Invalid prepaid usdt={usdt} rate={rate_d} kzt={kzt_amount}")

    ensure_kzt_balances(merchant)
    merchant.refresh_from_db()
    blockchain = Balance.objects.get(type=3)
    tx_type = TransactionType.objects.get(name="Deposit")
    text = comment or f"Manual crypto prepaid {usdt} USDT @ {rate_d} = {kzt_amount} KZT"
    return Transaction.create(
        merchant.balance_kzt,
        blockchain,
        _transaction_type=tx_type,
        value=kzt_amount,
        _comment=text,
    )


def melbet_kzt_test_trader_username(merchant: Merchant | None) -> str | None:
    """Тестовый трейдер в роутинге — только для melbet KZT мерчантов (не для всех C2CKZT)."""
    if not is_melbet_merchant(merchant):
        return None
    name = (getattr(settings, "MELBET_KZT_TEST_TRADER_USERNAME", None) or "").strip()
    return name or None


def get_melbet_merchant(username: str | None = None) -> Merchant | None:
    if username:
        user = User.objects.filter(username=username).first()
        if user is None:
            return None
        return Merchant.objects.filter(user=user).first()
    for name in (MELBET_USERNAME, MELBET_TEST_USERNAME):
        if name not in melbet_kzt_usernames():
            continue
        user = User.objects.filter(username=name).first()
        if user is None:
            continue
        merchant = Merchant.objects.filter(user=user).first()
        if merchant is not None:
            return merchant
    return None
