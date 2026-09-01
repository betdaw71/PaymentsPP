from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError

from basics.models import Balance, Currency, PaymentSystem
from merchant.kzt_settlement import (
    MELBET_TEST_USERNAME,
    MELBET_USERNAME,
    balance_allows_negative_ledger,
    ensure_kzt_balances,
    in_order_credit_kzt,
    is_melbet_merchant,
    merchant_fee_in_kzt,
    out_order_freeze_kzt,
    uses_melbet_kzt_settlement,
)
from merchant.models import Merchant
from trade.models import Transaction, TransactionType


class KztSettlementHelpersTest(TestCase):
    def test_fee_and_order_amounts(self):
        self.assertEqual(merchant_fee_in_kzt(Decimal("10000"), Decimal("2.5")), Decimal("250.00"))
        order = SimpleNamespace(amount=Decimal("10000"), merchant_fee=Decimal("250"))
        self.assertEqual(in_order_credit_kzt(order), Decimal("9750.00"))
        out = SimpleNamespace(amount=Decimal("5000"), merchant_fee=Decimal("150"))
        self.assertEqual(out_order_freeze_kzt(out), Decimal("5150.00"))

    @override_settings(MELBET_KZT_USERNAMES="melbet,melbet_test")
    def test_is_melbet_merchant_usernames(self):
        melbet_user = User.objects.create_user(username=MELBET_USERNAME, password="x")
        test_user = User.objects.create_user(username=MELBET_TEST_USERNAME, password="x")
        other_user = User.objects.create_user(username="other_merchant", password="x")
        melbet_m = Merchant.objects.create(user=melbet_user)
        test_m = Merchant.objects.create(user=test_user)
        other_m = Merchant.objects.create(user=other_user)
        self.assertTrue(is_melbet_merchant(melbet_m))
        self.assertTrue(is_melbet_merchant(test_m))
        self.assertFalse(is_melbet_merchant(other_m))
        self.assertFalse(is_melbet_merchant(None))

    @override_settings(MELBET_KZT_USERNAMES="melbet")
    def test_uses_melbet_kzt_only_c2ckzt(self):
        user = User.objects.create_user(username=MELBET_USERNAME, password="x")
        merchant = Merchant.objects.create(user=user)
        currency = Currency.objects.create(symbol="KZT", name="Tenge")
        c2c = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=currency,
            required_fields={},
        )
        rub = Currency.objects.create(symbol="RUB", name="Ruble")
        sber = PaymentSystem.objects.create(
            name="Sber",
            currency=rub,
            required_fields={},
        )
        self.assertTrue(uses_melbet_kzt_settlement(merchant, c2c))
        self.assertFalse(uses_melbet_kzt_settlement(merchant, sber))
        self.assertFalse(uses_melbet_kzt_settlement(merchant, None))

    def test_ensure_kzt_balances_creates_accounts(self):
        user = User.objects.create_user(username="kzt_bal_user", password="x")
        merchant = Merchant.objects.create(user=user)
        self.assertIsNone(merchant.balance_kzt_id)
        ensure_kzt_balances(merchant)
        merchant.refresh_from_db()
        self.assertIsNotNone(merchant.balance_kzt_id)
        self.assertIsNotNone(merchant.frozen_balance_kzt_id)
        self.assertEqual(merchant.balance_kzt.amount, Decimal("0"))
        ensure_kzt_balances(merchant)
        first_kzt_id = merchant.balance_kzt_id
        merchant.refresh_from_db()
        self.assertEqual(merchant.balance_kzt_id, first_kzt_id)

    def test_balance_allows_negative_for_kzt_ledgers(self):
        user = User.objects.create_user(username="neg_kzt", password="x")
        merchant = Merchant.objects.create(user=user)
        ensure_kzt_balances(merchant)
        merchant.refresh_from_db()
        self.assertTrue(balance_allows_negative_ledger(merchant.balance_kzt))
        self.assertTrue(balance_allows_negative_ledger(merchant.frozen_balance_kzt))
        plain = Balance.objects.create(type=0, amount=Decimal("10"))
        self.assertFalse(balance_allows_negative_ledger(plain))


class KztTransactionNegativeBalanceTest(TestCase):
    def setUp(self):
        self.blockchain, _ = Balance.objects.get_or_create(type=3, defaults={"amount": Decimal("1000000")})
        self.tx_type, _ = TransactionType.objects.get_or_create(name="Deposit")

    def test_debit_below_zero_allowed_on_balance_kzt(self):
        user = User.objects.create_user(username=MELBET_TEST_USERNAME, password="x")
        merchant = Merchant.objects.create(user=user)
        ensure_kzt_balances(merchant)
        merchant.refresh_from_db()
        merchant.balance_kzt.amount = Decimal("100")
        merchant.balance_kzt.save(update_fields=["amount"])
        platform = Balance.objects.create(type=2, amount=Decimal("0"))
        Transaction.create(
            merchant.balance_kzt,
            platform,
            value=Decimal("500"),
            _transaction_type=self.tx_type,
            _comment="test overdraft",
        )
        merchant.balance_kzt.refresh_from_db()
        self.assertEqual(merchant.balance_kzt.amount, Decimal("-400"))

    def test_debit_melbet_crypto_prepaid_goes_negative(self):
        from merchant.kzt_settlement import debit_melbet_crypto_prepaid

        user = User.objects.create_user(username=MELBET_USERNAME, password="x")
        merchant = Merchant.objects.create(user=user)
        ensure_kzt_balances(merchant)
        merchant.refresh_from_db()
        merchant.balance_kzt.amount = Decimal("-1000000.00")
        merchant.balance_kzt.save(update_fields=["amount"])
        tx = debit_melbet_crypto_prepaid(
            merchant,
            usdt_amount=Decimal("2500"),
            rate=Decimal("479.3"),
        )
        merchant.balance_kzt.refresh_from_db()
        self.assertEqual(tx.value, Decimal("1198250.00"))
        self.assertEqual(tx.from_balance_id, merchant.balance_kzt_id)
        self.assertEqual(merchant.balance_kzt.amount, Decimal("-2198250.00"))
        self.assertIn("2500", tx.comment)
        self.assertIn("479.3", tx.comment)

    def test_debit_below_zero_blocked_on_regular_balance(self):
        user = User.objects.create_user(username="regular_m", password="x")
        balance = Balance.objects.create(type=0, amount=Decimal("100"))
        Merchant.objects.create(user=user, balance=balance)
        platform = Balance.objects.create(type=2, amount=Decimal("0"))
        with self.assertRaises(ValidationError):
            Transaction.create(
                balance,
                platform,
                value=Decimal("500"),
                _transaction_type=self.tx_type,
                _comment="should fail",
            )
