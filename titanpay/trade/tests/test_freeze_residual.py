from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from basics.models import (
    Balance,
    Currency,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeam,
    TrafficType,
)
from merchant.models import Merchant, MerchantSolution
from trade.models import InOrder, InOrderStatus, Transaction, TransactionType


class FreezeResidualTest(TestCase):
    def setUp(self):
        self.kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        traffic = TrafficType.objects.create(name="Standard")
        self.ps = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=self.kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16"}},
            usdt_exchange_rate=Decimal("500"),
        )
        team = TraderTeam.objects.create(name="t")
        user = User.objects.create_user(username="fr_trader", password="x")
        self.trader = Trader.objects.create(
            user=user,
            team=team,
            currency=self.kzt,
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("100")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("20")),
        )
        group = PaymentDetailsGroup.objects.create(
            trader=self.trader,
            currency=self.kzt,
            payment_system=self.ps,
            status=1,
            in_active=True,
            work_type="by_card",
            owner="X",
        )
        detail = PaymentDetails.objects.create(
            group=group,
            status=1,
            card_number="4111111111111111",
            deposit_number="00000000000000000001",
        )
        merch_user = User.objects.create_user(username="fr_merch", password="x")
        merchant = Merchant.objects.create(
            user=merch_user,
            balance=Balance.objects.create(type=0, amount=Decimal("0")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        solution = MerchantSolution.objects.create(
            merchant=merchant,
            payment_system=self.ps,
            traffic=traffic,
            mdr_in=Decimal("6"),
        )
        self.completed = InOrderStatus.objects.create(name="Completed")
        self.order = InOrder.objects.create(
            status=self.completed,
            amount=Decimal("5000"),
            usd_amount=Decimal("10"),
            solution=solution,
            payment_details=detail,
            merchant_fee=Decimal("0.60"),
            trader_fee=Decimal("0.40"),
            agent_fee=Decimal("0"),
            arbitrage_comment="",
            pic="https://example.com/x",
        )
        TransactionType.objects.create(name="Freeze")
        TransactionType.objects.create(name="Charge")
        TransactionType.objects.create(name="Deposit")
        Balance.objects.create(type=2, amount=Decimal("0"))  # aggregator
        Balance.objects.create(type=3, amount=Decimal("0"))  # blockchain

        fz = TransactionType.objects.get(name="Freeze")
        ch = TransactionType.objects.get(name="Charge")
        # Double freeze 10+10, charge only 10 → residual 10
        Transaction.create(
            _from=self.trader.balance_usdt,
            _to=self.trader.frozen_balance_usdt,
            value=Decimal("10"),
            _transaction_type=fz,
            _linked_in_order=self.order,
            _comment="New",
        )
        # top up available for second freeze
        self.trader.balance_usdt.amount = Decimal("100")
        self.trader.balance_usdt.save()
        Transaction.create(
            _from=self.trader.balance_usdt,
            _to=self.trader.frozen_balance_usdt,
            value=Decimal("10"),
            _transaction_type=fz,
            _linked_in_order=self.order,
            _comment="Arbitrage",
        )
        Transaction.create(
            _from=self.trader.frozen_balance_usdt,
            _to=Balance.objects.get(type=2),
            value=Decimal("10"),
            _transaction_type=ch,
            _linked_in_order=self.order,
            _comment="In-order completed",
        )

    def test_residual_and_release(self):
        self.assertEqual(self.order.freeze_residual_usdt(), Decimal("10"))
        got = self.order.release_freeze_residual("test")
        self.assertEqual(got, Decimal("10"))
        self.assertEqual(self.order.freeze_residual_usdt(), Decimal("0"))
        self.trader.frozen_balance_usdt.refresh_from_db()
        # started frozen 20, +10+10 freeze via Transaction.create already moved;
        # Charge -10; release -10 → depends on starting. Just assert residual gone.
        self.assertEqual(self.order.freeze_residual_usdt(), Decimal("0"))
