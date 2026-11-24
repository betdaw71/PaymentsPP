from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from appeals.services import _save_order_pic, _try_order_arbitrage
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
from trade.models import InOrder, InOrderStatus, TransactionType


class AppealArbitrageInsuranceTest(TestCase):
    def setUp(self):
        self.kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        traffic = TrafficType.objects.create(name="Standard")
        ps = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=self.kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16"}},
            usdt_exchange_rate=Decimal("500"),
        )
        self.team = TraderTeam.objects.create(name="resdfe", insurance_deposit=Decimal("4.00"))
        user = User.objects.create_user(username="arb_trader", password="x")
        self.working = Balance.objects.create(type=0, amount=Decimal("1.00"))
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
        merch_user = User.objects.create_user(username="arb_merch", password="x")
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
        self.new = InOrderStatus.objects.create(name="New")
        self.arbitrage = InOrderStatus.objects.create(name="Arbitrage")
        TransactionType.objects.create(name="Freeze")
        TransactionType.objects.create(name="Deposit")
        Balance.objects.create(type=3, amount=Decimal("1000"))

    def _order(self, status, usd="10.00", working="1.00"):
        self.working.amount = Decimal(working)
        self.working.save(update_fields=["amount"])
        self.frozen.amount = Decimal("0")
        self.frozen.save(update_fields=["amount"])
        return InOrder.objects.create(
            status=status,
            amount=Decimal("5000"),
            usd_amount=Decimal(usd),
            solution=self.solution,
            payment_details=self.detail,
            merchant_fee=Decimal("0"),
            trader_fee=Decimal("0"),
            agent_fee=Decimal("0"),
            arbitrage_comment="",
            pic="https://example.com/old",
        )

    def test_expired_appeal_debits_insurance_and_sets_arbitrage(self):
        order = self._order(self.expired, usd="10.00", working="1.00")

        _try_order_arbitrage(order)

        order.refresh_from_db()
        self.working.refresh_from_db()
        self.frozen.refresh_from_db()
        self.team.refresh_from_db()
        self.assertEqual(order.status_id, self.arbitrage.id)
        self.assertEqual(self.working.amount, Decimal("0.00"))
        self.assertEqual(self.frozen.amount, Decimal("10.00"))
        self.assertEqual(self.team.insurance_deposit, Decimal("-5.00"))

    def test_enough_working_balance_does_not_touch_insurance(self):
        order = self._order(self.expired, usd="10.00", working="20.00")

        _try_order_arbitrage(order)

        order.refresh_from_db()
        self.working.refresh_from_db()
        self.frozen.refresh_from_db()
        self.team.refresh_from_db()
        self.assertEqual(order.status_id, self.arbitrage.id)
        self.assertEqual(self.working.amount, Decimal("10.00"))
        self.assertEqual(self.frozen.amount, Decimal("10.00"))
        self.assertEqual(self.team.insurance_deposit, Decimal("4.00"))

    def test_open_order_changes_status_without_a_second_freeze(self):
        self.frozen.amount = Decimal("10.00")
        self.frozen.save(update_fields=["amount"])
        order = self._order(self.new, usd="10.00", working="5.00")
        self.frozen.amount = Decimal("10.00")
        self.frozen.save(update_fields=["amount"])

        _try_order_arbitrage(order)

        order.refresh_from_db()
        self.working.refresh_from_db()
        self.frozen.refresh_from_db()
        self.team.refresh_from_db()
        self.assertEqual(order.status_id, self.arbitrage.id)
        self.assertEqual(order.arbitrage_comment, "Arbitrage due to inactivity")
        self.assertEqual(self.working.amount, Decimal("5.00"))
        self.assertEqual(self.frozen.amount, Decimal("10.00"))
        self.assertEqual(self.team.insurance_deposit, Decimal("4.00"))

    def test_receipt_url_is_stored_on_the_order(self):
        order = self._order(self.expired)
        url = "https://cdn.example.com/" + ("a" * 180) + "/appeals/receipt.pdf"
        self.assertGreater(len(url), 200)
        self.assertLessEqual(len(url), 500)

        _save_order_pic(order, url)

        order.refresh_from_db()
        self.assertEqual(order.pic, url)

    def test_freeze_attribute_error_still_forces_arbitrage(self):
        """Melbet Expired + broken trader balances must not abort the appeal."""
        order = self._order(self.expired, usd="10.00", working="1.00")
        self.trader.balance_usdt = None
        self.trader.frozen_balance_usdt = None
        self.trader.save(update_fields=["balance_usdt", "frozen_balance_usdt"])

        _try_order_arbitrage(order)

        order.refresh_from_db()
        self.assertEqual(order.status_id, self.arbitrage.id)

    def test_zero_working_balance_still_opens_appeal_arbitrage(self):
        """При 0 на ЛК и страховом депозите апелляция всё равно уходит в Arbitrage."""
        self.team.insurance_deposit = Decimal("50.00")
        self.team.save(update_fields=["insurance_deposit"])
        order = self._order(self.expired, usd="10.00", working="0.00")

        _try_order_arbitrage(order)

        order.refresh_from_db()
        self.working.refresh_from_db()
        self.frozen.refresh_from_db()
        self.team.refresh_from_db()
        self.assertEqual(order.status_id, self.arbitrage.id)
        self.assertEqual(self.working.amount, Decimal("0.00"))
        self.assertEqual(self.frozen.amount, Decimal("10.00"))
        self.assertEqual(self.team.insurance_deposit, Decimal("40.00"))

    def test_support_arbitrage_debits_insurance_at_zero_balance(self):
        """Кнопка support arbitrage при 0 балансе списывает страховой депозит."""
        self.team.insurance_deposit = Decimal("25.00")
        self.team.save(update_fields=["insurance_deposit"])
        order = self._order(self.expired, usd="10.00", working="0.00")

        order.arbitrage_support()

        order.refresh_from_db()
        self.working.refresh_from_db()
        self.frozen.refresh_from_db()
        self.team.refresh_from_db()
        self.assertEqual(order.status_id, self.arbitrage.id)
        self.assertEqual(order.arbitrage_comment, "Arbitrage called by support")
        self.assertEqual(self.working.amount, Decimal("0.00"))
        self.assertEqual(self.frozen.amount, Decimal("10.00"))
        self.assertEqual(self.team.insurance_deposit, Decimal("15.00"))
