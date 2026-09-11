from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from basics.models import Balance, Language, TeamLead
from trade.models import TransactionType, WithdrawalRequest


class TeamLeadWithdrawalTests(TestCase):
    def setUp(self):
        TransactionType.objects.create(name="Freeze")
        TransactionType.objects.create(name="Withdrawal")
        TransactionType.objects.create(name="Deposit")
        lang = Language.objects.create(name="Russian")
        self.user = User.objects.create_user(username="tl_withdraw", password="x")
        available = Balance.objects.create(type=0, amount=Decimal("780.00"))
        self.teamlead = TeamLead.objects.create(user=self.user, language=lang, balance=available)

    def test_create_does_not_require_trader(self):
        req = WithdrawalRequest.create(
            amount=Decimal("780.00"),
            _from=self.teamlead.balance,
            address_to="TCwCHZ5na6cJDwXrzVKFiixdC9qXXXXX",
            from_user=self.user,
        )
        self.teamlead.refresh_from_db()
        self.assertEqual(req.status, 0)
        self.assertIsNotNone(self.teamlead.frozen_balance_id)
        self.assertEqual(self.teamlead.balance.amount, Decimal("0.00"))
        self.assertEqual(self.teamlead.frozen_balance.amount, Decimal("780.00"))
        self.assertFalse(hasattr(self.user, "trader"))
