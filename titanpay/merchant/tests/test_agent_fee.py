from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from basics.models import Balance, Language
from merchant.agent_fee import compute_in_order_agent_fee
from merchant.models import Agent, Merchant


@override_settings(MELBET_KZT_USERNAMES="melbet", MELBET_KZT_PS_NAMES="C2CKZT")
class AgentFeeComputeTest(TestCase):
    def setUp(self):
        Language.objects.create(name="Russian")
        self.agent_user = User.objects.create_user(username="L_payments", password="x")
        self.agent = Agent.objects.create(
            user=self.agent_user,
            balance=Balance.objects.create(type=0, amount=Decimal("0")),
            commission_percent=Decimal("0.20"),
        )
        self.melbet_user = User.objects.create_user(username="melbet", password="x")
        self.merchant = Merchant.objects.create(
            user=self.melbet_user,
            balance=Balance.objects.create(type=0, amount=Decimal("0")),
            agent=self.agent,
        )

    def test_kzt_turnover_converts_to_usdt(self):
        ps = SimpleNamespace(name="C2CKZT")
        order = SimpleNamespace(
            amount=Decimal("100000"),
            usd_amount=Decimal("200"),
            solution=SimpleNamespace(merchant=self.merchant, payment_system=ps),
        )
        # 0.2% of 100000 KZT = 200 KZT → 200 * 200/100000 = 0.40 USDT
        self.assertEqual(compute_in_order_agent_fee(order), Decimal("0.40"))

    def test_no_agent_is_zero(self):
        self.merchant.agent = None
        self.merchant.save()
        ps = SimpleNamespace(name="C2CKZT")
        order = SimpleNamespace(
            amount=Decimal("100000"),
            usd_amount=Decimal("200"),
            solution=SimpleNamespace(merchant=self.merchant, payment_system=ps),
        )
        self.assertEqual(compute_in_order_agent_fee(order), Decimal("0"))
