from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from basics.models import (
    Balance,
    Currency,
    Language,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeam,
    TrafficType,
)
from trade.models import Transaction, TransactionType
from trade.routing.base import route


@override_settings(PAYPLAT_TRADER_USERNAME="payplat1")
class PspCreditRoutingTest(TestCase):
    def setUp(self):
        self.kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        Language.objects.create(name="Russian")
        self.traffic = TrafficType.objects.create(name="Standard")
        self.c2ckzt = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=self.kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}},
            usdt_exchange_rate=Decimal("500"),
        )
        team = TraderTeam.objects.create(name="psp")
        user = User.objects.create_user(username="payplat1", password="x")
        self.trader = Trader.objects.create(
            user=user,
            team=team,
            currency=self.kzt,
            credit_limit=Decimal("50000"),
            working_deposit=Decimal("12000"),
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("0")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.group = PaymentDetailsGroup.objects.create(
            trader=self.trader,
            currency=self.kzt,
            payment_system=self.c2ckzt,
            status=1,
            in_active=True,
            work_type="by_card",
            owner="PAYPLAT",
            limit_per_period=Decimal("1000000"),
        )
        PaymentDetails.objects.create(
            group=self.group,
            status=1,
            card_number="4111111111111111",
            deposit_number="00000000000000000002",
        )
        TransactionType.objects.create(name="Freeze")
        TransactionType.objects.create(name="Charge")
        TransactionType.objects.create(name="Deposit")
        Balance.objects.create(type=3, amount=Decimal("0"))

    def test_zero_available_still_in_cascade(self):
        router = route(self.c2ckzt)
        usd = Decimal("20")
        options = router.get_possible_options_in(None, self.c2ckzt, Decimal("10000"), self.traffic, usd)
        self.assertTrue(options.filter(id=self.group.id).exists())

    def test_below_credit_floor_excluded(self):
        self.trader.balance_usdt.amount = Decimal("-50000")
        self.trader.balance_usdt.save()
        router = route(self.c2ckzt)
        usd = Decimal("20")
        options = router.get_possible_options_in(None, self.c2ckzt, Decimal("10000"), self.traffic, usd)
        self.assertFalse(options.filter(id=self.group.id).exists())

    def test_freeze_may_go_negative_within_limit(self):
        Transaction.create(
            _from=self.trader.balance_usdt,
            _to=self.trader.frozen_balance_usdt,
            value=Decimal("100"),
            _transaction_type=TransactionType.objects.get(name="Freeze"),
        )
        self.trader.balance_usdt.refresh_from_db()
        self.assertEqual(self.trader.balance_usdt.amount, Decimal("-100"))
