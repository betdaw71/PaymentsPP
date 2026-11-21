from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from basics.models import (
    Balance,
    Currency,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TrafficType,
)
from merchant.models import Merchant, MerchantSolution
from trade.models import InOrder, InOrderStatus
from trade.routing.fair_pick import pick_least_loaded_detail


class FairPickTest(TestCase):
    def setUp(self):
        kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        traffic = TrafficType.objects.create(name="Standard")
        ps = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16"}},
            usdt_exchange_rate=Decimal("500"),
        )
        user = User.objects.create_user(username="fair_trader", password="x")
        trader = Trader.objects.create(
            user=user,
            currency=kzt,
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("1000")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.group = PaymentDetailsGroup.objects.create(
            trader=trader,
            currency=kzt,
            payment_system=ps,
            status=1,
            in_active=True,
            work_type="by_card",
            owner="DROP",
        )
        self.busy = PaymentDetails.objects.create(
            group=self.group,
            status=1,
            card_number="4111111111111111",
            deposit_number="00000000000000000001",
        )
        self.idle = PaymentDetails.objects.create(
            group=self.group,
            status=1,
            card_number="4222222222222222",
            deposit_number="00000000000000000002",
        )
        merch_user = User.objects.create_user(username="fair_merch", password="x")
        merchant = Merchant.objects.create(
            user=merch_user,
            balance=Balance.objects.create(type=0, amount=Decimal("0")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        solution = MerchantSolution.objects.create(
            merchant=merchant,
            payment_system=ps,
            traffic=traffic,
            mdr_in=Decimal("6"),
        )
        st_new = InOrderStatus.objects.create(name="New")
        InOrder.objects.create(
            amount=Decimal("1000"),
            usd_amount=Decimal("2"),
            payment_details=self.busy,
            status=st_new,
            solution=solution,
            arbitrage_comment="",
            pic="https://example.com/x",
            creation_date=timezone.now(),
        )

    def test_prefers_card_with_fewer_open_orders(self):
        qs = PaymentDetails.objects.filter(group=self.group, status=1)
        picked = pick_least_loaded_detail(qs)
        self.assertEqual(picked.id, self.idle.id)
