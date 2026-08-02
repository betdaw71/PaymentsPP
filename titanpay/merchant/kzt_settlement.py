"""Melbet merchant settlement in KZT (C2CKZT) — separate from USDT merchant.balance."""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from basics.models import Balance, Currency, PaymentSystem
from merchant.models import Merchant

MELBET_USERNAME = "melbet"
KZT_PS_NAME = "C2CKZT"


def is_melbet_merchant(merchant: Merchant | None) -> bool:
    if merchant is None or not getattr(merchant, "user", None):
        return False
    return merchant.user.username == MELBET_USERNAME


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


def get_melbet_merchant() -> Merchant | None:
    user = User.objects.filter(username=MELBET_USERNAME).first()
    if user is None:
        return None
    return Merchant.objects.filter(user=user).first()
