"""Support recalculate must re-quote dual FX. A stale psp_usd charges the old sum."""
from decimal import Decimal
from unittest.mock import patch

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
    TraderTeamRates,
    TrafficType,
)
from merchant.models import Merchant, MerchantSolution
from payments.models import PayIn, PayInStatus
from trade.models import InOrder, InOrderStatus, Transaction, TransactionType


class SupportRecalculateDualFxTest(TestCase):
    def setUp(self):
        kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        traffic = TrafficType.objects.create(name="Standard")
        self.ps = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16"}},
            usdt_exchange_rate=Decimal("525"),
        )
        self.team = TraderTeam.objects.create(name="resdfe-team", rate_in=Decimal("0"))
        TraderTeamRates.objects.create(
            team=self.team,
            payment_system=self.ps,
            mdr_in=Decimal("4"),
            mdr_out=Decimal("0"),
        )
        user = User.objects.create_user(username="resdfe", password="x")
        self.trader = Trader.objects.create(
            user=user,
            team=self.team,
            currency=kzt,
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("100")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.group = PaymentDetailsGroup.objects.create(
            trader=self.trader,
            currency=kzt,
            payment_system=self.ps,
            status=1,
            in_active=True,
            work_type="by_card",
            owner="X",
            current_volume=Decimal("5000"),
        )
        detail = PaymentDetails.objects.create(
            group=self.group,
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
            mdr_in=Decimal("7"),
        )
        recalc = InOrderStatus.objects.create(name="Recalculation")
        InOrderStatus.objects.create(name="Completed")
        # Stale quote for 5 000 ₸. Support will confirm 10 500 ₸.
        self.order = InOrder.objects.create(
            status=recalc,
            amount=Decimal("5000"),
            usd_amount=Decimal("9.52"),
            merchant_rate=Decimal("525"),
            psp_rate=Decimal("520"),
            psp_usd_amount=Decimal("9.62"),
            solution=solution,
            payment_details=detail,
            merchant_fee=Decimal("350"),
            trader_fee=Decimal("0.38"),
            agent_fee=Decimal("0"),
            arbitrage_comment="",
            pic="https://example.com/x",
        )
        TransactionType.objects.create(name="Freeze")
        TransactionType.objects.create(name="Charge")
        TransactionType.objects.create(name="Deposit")
        Balance.objects.create(type=2, amount=Decimal("0"))
        Balance.objects.create(type=3, amount=Decimal("0"))
        Transaction.create(
            _from=self.trader.balance_usdt,
            _to=self.trader.frozen_balance_usdt,
            value=Decimal("9.62"),
            _transaction_type=TransactionType.objects.get(name="Freeze"),
            _linked_in_order=self.order,
            _comment="New",
        )
        pay_status = PayInStatus.objects.create(name="In Progress")
        PayIn.objects.create(
            amount=Decimal("5000"),
            currency=kzt,
            payment_system=self.ps,
            merchant_order_id="recalc-1",
            callback_url="https://example.com/cb",
            status=pay_status,
            merchant=merchant,
            order=self.order,
        )

    def test_support_recalc_charges_new_psp_usd_not_stale(self):
        with patch("payments.models.PayIn.send_callback", return_value=200):
            self.order.recalculate(Decimal("10500"))

        self.order.refresh_from_db()
        self.group.refresh_from_db()
        self.assertEqual(self.order.amount, Decimal("10500.00"))
        self.assertEqual(self.order.usd_amount, Decimal("20.00"))
        self.assertEqual(self.order.psp_usd_amount, Decimal("20.19"))
        self.assertEqual(self.order.trader_fee, Decimal("0.81"))
        self.assertEqual(self.group.current_volume, Decimal("10500.00"))

        charge = Transaction.objects.get(
            linked_in_order=self.order,
            transaction_type__name="Charge",
            comment="In-order completed",
        )
        self.assertEqual(charge.value, Decimal("20.19"))
