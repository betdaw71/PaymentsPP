from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from basics.models import Balance, Language
from merchant.models import Agent
from trade.ledger import user_balance_ids
from trade.models import TransactionType, WithdrawalRequest, withdrawal_frozen_balance


class AgentCabinetTest(TestCase):
    def setUp(self):
        Language.objects.create(name="Russian")
        TransactionType.objects.create(name="Freeze")
        TransactionType.objects.create(name="Deposit")
        TransactionType.objects.create(name="Withdrawal")
        self.user = User.objects.create_user(username="L_payments", password="secret")
        self.agent = Agent.objects.create(
            user=self.user,
            balance=Balance.objects.create(type=0, amount=Decimal("100.00")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
            commission_percent=Decimal("0.20"),
        )

    def test_balance_ids_and_frozen(self):
        ids = user_balance_ids(self.user)
        self.assertIn(self.agent.balance_id, ids)
        self.assertIn(self.agent.frozen_balance_id, ids)
        frozen = withdrawal_frozen_balance(self.user)
        self.assertEqual(frozen.id, self.agent.frozen_balance_id)

    def test_create_withdrawal(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.post(
            "/api/v1/trade/withdrawal-request/",
            {"amount": "40.00", "address": "0x" + "a" * 40},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.agent.balance.refresh_from_db()
        self.agent.frozen_balance.refresh_from_db()
        self.assertEqual(self.agent.balance.amount, Decimal("60.00"))
        self.assertEqual(self.agent.frozen_balance.amount, Decimal("40.00"))
        self.assertEqual(WithdrawalRequest.objects.filter(from_user=self.user).count(), 1)
