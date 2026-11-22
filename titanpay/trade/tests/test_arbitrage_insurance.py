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
from trade.models import InOrder, InOrderStatus, TransactionType, cover_freeze_from_insurance


class ArbitrageInsuranceCoverTest(TestCase):
    def setUp(self):
        self.kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        traffic = TrafficType.objects.create(name="Standard")
        ps = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=self.kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16"}},
            usdt_exchange_rate=Decimal("500"),
        )
        self.team = TraderTeam.objects.create(name="ins-team", insurance_deposit=Decimal("100.00"))
        user = User.objects.create_user(username="ins_trader", password="x")
        self.working = Balance.objects.create(type=0, amount=Decimal("0"))
        self.frozen = Balance.objects.create(type=1, amount=Decimal("0"))
        self.trader = Trader.objects.create(
            user=user,
            team=self.team,
            currency=self.kzt,
            balance_usdt=self.working,
            frozen_balance_usdt=self.frozen,
        )
        group = PaymentDetailsGroup.objects.create(
            trader=self.trader,
            currency=self.kzt,
            payment_system=ps,
            status=1,
            in_active=True,
            work_type="by_card",
            owner="X",
        )
        self.detail = PaymentDetails.objects.create(
            group=group,
            status=1,
            card_number="4111111111111111",
            deposit_number="00000000000000000001",
        )
        merch_user = User.objects.create_user(username="ins_merch", password="x")
        merchant = Merchant.objects.create(
            user=merch_user,
            balance=Balance.objects.create(type=0, amount=Decimal("0")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.solution = MerchantSolution.objects.create(
            merchant=merchant,
            payment_system=ps,
            traffic=traffic,
            mdr_in=Decimal("6"),
        )
        self.expired = InOrderStatus.objects.create(name="Expired")
        self.cancelled = InOrderStatus.objects.create(name="Cancelled")
        self.arbitrage = InOrderStatus.objects.create(name="Arbitrage")
        TransactionType.objects.create(name="Freeze")
        TransactionType.objects.create(name="Deposit")
        Balance.objects.create(type=3, amount=Decimal("1000"))

    def _order(self, status, usd="12.00"):
        self.working.amount = Decimal("0")
        self.working.save(update_fields=["amount"])
        self.frozen.amount = Decimal("0")
        self.frozen.save(update_fields=["amount"])
        return InOrder.objects.create(
            status=status,
            amount=Decimal("6000"),
            usd_amount=Decimal(usd),
            solution=self.solution,
            payment_details=self.detail,
            merchant_fee=Decimal("0"),
            trader_fee=Decimal("0"),
            agent_fee=Decimal("0"),
            arbitrage_comment="",
        )

    def test_cover_freeze_from_insurance_tops_up_working(self):
        order = self._order(self.expired, usd="12.00")
        covered = cover_freeze_from_insurance(order)

        self.working.refresh_from_db()
        self.team.refresh_from_db()
        self.assertEqual(covered, Decimal("12.00"))
        self.assertEqual(self.working.amount, Decimal("12.00"))
        self.assertEqual(self.team.insurance_deposit, Decimal("88.00"))

    def test_arbitrage_at_zero_balance_uses_insurance(self):
        order = self._order(self.cancelled, usd="12.00")

        order.arbitrage()

        order.refresh_from_db()
        self.working.refresh_from_db()
        self.frozen.refresh_from_db()
        self.team.refresh_from_db()
        self.assertEqual(order.status_id, self.arbitrage.id)
        self.assertEqual(self.working.amount, Decimal("0.00"))
        self.assertEqual(self.frozen.amount, Decimal("12.00"))
        self.assertEqual(self.team.insurance_deposit, Decimal("88.00"))

    def test_arbitrage_support_at_zero_balance_uses_insurance(self):
        order = self._order(self.expired, usd="12.00")

        order.arbitrage_support()

        order.refresh_from_db()
        self.working.refresh_from_db()
        self.frozen.refresh_from_db()
        self.team.refresh_from_db()
        self.assertEqual(order.status_id, self.arbitrage.id)
        self.assertEqual(self.working.amount, Decimal("0.00"))
        self.assertEqual(self.frozen.amount, Decimal("12.00"))
        self.assertEqual(self.team.insurance_deposit, Decimal("88.00"))
