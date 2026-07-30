from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from basics.models import Balance, Currency, Language, PaymentDetails, PaymentDetailsGroup, TeamLead, Trader, TraderTeam, \
    TraderTeamRates, TrafficType, PaymentSystem
from merchant.models import Merchant, MerchantSolution, MerchantAgentAssignment
from trade.agent_commission import (
    calculate_agent_fee,
    accrue_agent_commission_for_in_order,
    reverse_agent_commission_for_in_order,
    prepare_in_order_recalc_agent,
    AGENT_COMMISSION_COMMENT,
)
from trade.models import InOrder, InOrderStatus, Transaction, TransactionType
from titanpay.settings import SBER_NAME


class AgentCommissionUtilsTest(TestCase):
    def test_calculate_agent_fee(self):
        self.assertEqual(calculate_agent_fee(Decimal("100"), Decimal("0.5")), Decimal("0.50"))
        self.assertEqual(calculate_agent_fee(Decimal("0"), Decimal("1")), Decimal("0.00"))


class AgentCommissionInOrderTest(TestCase):
    def setUp(self):
        self.currency = Currency.objects.create(name="Ruble", symbol="RUB")
        Language.objects.create(name="English")
        self.traffic = TrafficType.objects.create(name="Gamble")
        fields = {"card_number": {"regex": "^\\d{16}$", "pattern": "X"}}
        self.ps = PaymentSystem.objects.create(
            name=SBER_NAME, currency=self.currency, required_fields=fields, sbp_compatible=True
        )
        for name in ("Charge", "Deposit", "Freeze"):
            TransactionType.objects.create(name=name)
        if not Balance.objects.filter(type=2).exists():
            Balance.objects.create(type=2, amount=Decimal("1000000"))
        else:
            agg = Balance.objects.get(type=2)
            agg.amount = Decimal("1000000")
            agg.save()

        team = TraderTeam.objects.create(name="T1", rate_in=Decimal("4"), rate_out=Decimal("1"))
        trader_user = User.objects.create_user(username="trader_agent_t", password="x")
        self.trader = Trader.objects.create(
            user=trader_user,
            team=team,
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("5000")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
            currency=self.currency,
        )
        TraderTeamRates.objects.create(team=team, payment_system=self.ps, mdr_in=Decimal("4"), mdr_out=Decimal("1"))

        merch_user = User.objects.create_user(username="merchant_agent_t", password="x")
        self.merchant = Merchant.objects.create(
            user=merch_user,
            balance=Balance.objects.create(type=0, amount=Decimal("0")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.solution = MerchantSolution.objects.create(
            payment_system=self.ps,
            merchant=self.merchant,
            mdr_in=Decimal("6"),
            mdr_out=Decimal("3"),
            traffic=self.traffic,
        )

        agent_user = User.objects.create_user(username="agent_agent_t", password="x")
        self.agent = TeamLead.objects.create(
            user=agent_user,
            balance=Balance.objects.create(type=0, amount=Decimal("0")),
        )
        MerchantAgentAssignment.objects.create(
            merchant=self.merchant,
            agent=self.agent,
            turnover_percent_in=Decimal("1"),
            turnover_percent_out=Decimal("0"),
            is_active=True,
        )

        self.gr = PaymentDetailsGroup.objects.create(
            owner="Test", trader=self.trader, currency=self.currency, payment_system=self.ps, status=1
        )
        self.gr.allowed_traffic.add(self.traffic)
        self.pd = PaymentDetails.objects.create(group=self.gr, card_number="1111222233334444")

    def _minimal_in_order(self, usd_amount=Decimal("10")):
        status = InOrderStatus.objects.create(name="New")
        amount = usd_amount * self.ps.usdt_exchange_rate
        merchant_fee = self.solution.mdr_in * usd_amount / Decimal(100)
        trader_fee = Decimal("4") * usd_amount / Decimal(100)
        return InOrder.objects.create(
            status=status,
            amount=amount,
            usd_amount=usd_amount,
            solution=self.solution,
            payment_details=self.pd,
            merchant_fee=merchant_fee,
            trader_fee=trader_fee,
            arbitrage_comment="",
            pic="",
        )

    def test_accrue_on_complete_sets_balance_and_agent_fee(self):
        order = self._minimal_in_order(Decimal("100"))
        self.trader.frozen_balance_usdt.amount = Decimal("100")
        self.trader.frozen_balance_usdt.save()

        accrue_agent_commission_for_in_order(order)
        order.save(update_fields=["agent_fee"])

        self.assertEqual(order.agent_fee, Decimal("1.00"))
        self.agent.balance.refresh_from_db()
        self.assertEqual(self.agent.balance.amount, Decimal("1.00"))
        self.assertTrue(
            Transaction.objects.filter(
                linked_in_order=order, comment=AGENT_COMMISSION_COMMENT, value=Decimal("1.00")
            ).exists()
        )

    def test_recalc_reverses_then_reaccrues(self):
        order = self._minimal_in_order(Decimal("100"))
        accrue_agent_commission_for_in_order(order)
        order.save(update_fields=["agent_fee"])

        prepare_in_order_recalc_agent(order)
        order.usd_amount = Decimal("200")
        order.agent_fee = Decimal("0")
        accrue_agent_commission_for_in_order(order)
        order.save(update_fields=["agent_fee", "usd_amount"])

        self.assertEqual(order.agent_fee, Decimal("2.00"))
        self.agent.balance.refresh_from_db()
        self.assertEqual(self.agent.balance.amount, Decimal("2.00"))


class TeamleadScopeTest(TestCase):
    def test_invalid_scope_raises(self):
        from trade.teamlead_scope import teamlead_order_scope
        from rest_framework.exceptions import ValidationError

        class FakeRequest:
            query_params = {"scope": "hacker"}

        with self.assertRaises(ValidationError):
            teamlead_order_scope(FakeRequest())
