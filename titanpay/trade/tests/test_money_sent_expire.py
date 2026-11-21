"""Money sent by user без подтверждения трейдера → Expired после expired_time_in."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

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
from merchant.models import Merchant, MerchantSolution
from trade.models import InOrder, InOrderStatus, InOrderStatusChange, TransactionType
from trade.utils2 import expire


class MoneySentExpireTest(TestCase):
    def setUp(self):
        Language.objects.create(name="Russian")
        TransactionType.objects.get_or_create(name="Deposit")
        TransactionType.objects.get_or_create(name="Freeze")
        self.kzt = Currency.objects.create(name="Tenge MSE", symbol="KZT_MSE")
        self.ps = PaymentSystem.objects.create(
            name="C2CKZT_MSE",
            currency=self.kzt,
            required_fields={},
            usdt_exchange_rate=Decimal("500"),
            expired_time_in=timedelta(minutes=15),
        )
        traffic = TrafficType.objects.create(name="Standard MSE")
        team = TraderTeam.objects.create(name="mse-team")
        trader_user = User.objects.create_user(username="mse_trader", password="x")
        self.trader = Trader.objects.create(
            user=trader_user,
            team=team,
            currency=self.kzt,
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("1000")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("10")),
        )
        group = PaymentDetailsGroup.objects.create(
            trader=self.trader,
            currency=self.kzt,
            payment_system=self.ps,
            status=1,
            amount=Decimal("999999"),
            in_active=True,
            current_volume=Decimal("5000"),
        )
        group.allowed_traffic.add(traffic)
        self.detail = PaymentDetails.objects.create(
            group=group,
            status=1,
            card_number="4111111111111111",
            deposit_number="",
            amount=Decimal("0"),
        )
        merch_user = User.objects.create_user(username="mse_merch", password="x")
        merchant = Merchant.objects.create(
            user=merch_user,
            balance=Balance.objects.create(type=0, amount=Decimal("0")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.solution = MerchantSolution.objects.create(
            merchant=merchant,
            payment_system=self.ps,
            traffic=traffic,
            mdr_in=Decimal("6"),
        )
        InOrderStatus.objects.create(name="New")
        self.status_sent = InOrderStatus.objects.create(name="Money sent by user")
        InOrderStatus.objects.create(name="Expired")

    def _order(self, *, money_sent_ago: timedelta):
        order = InOrder.objects.create(
            status=self.status_sent,
            amount=Decimal("5000"),
            usd_amount=Decimal("10"),
            solution=self.solution,
            payment_details=self.detail,
            merchant_fee=Decimal("0.60"),
            trader_fee=Decimal("0.40"),
            agent_fee=Decimal("0"),
            arbitrage_comment="",
            pic="https://example.com/x",
        )
        sent_at = timezone.now() - money_sent_ago
        change = InOrderStatusChange.objects.create(
            order=order, status=self.status_sent, timedelta=0
        )
        InOrderStatusChange.objects.filter(pk=change.pk).update(created_at=sent_at)
        return order

    def test_money_sent_older_than_ttl_expires(self):
        order = self._order(money_sent_ago=timedelta(minutes=16))
        expire()
        order.refresh_from_db()
        self.assertEqual(order.status.name, "Expired")

    def test_money_sent_within_ttl_stays(self):
        order = self._order(money_sent_ago=timedelta(minutes=5))
        expire()
        order.refresh_from_db()
        self.assertEqual(order.status.name, "Money sent by user")

    def test_ttl_uses_first_money_sent_like_ui(self):
        """ЛК: expires_at = first().created_at + ttl; повторная запись не сбрасывает таймер."""
        order = self._order(money_sent_ago=timedelta(minutes=20))
        # «свежая» повторная Money-sent — expire всё равно должен закрыть по первой
        recent = InOrderStatusChange.objects.create(
            order=order, status=self.status_sent, timedelta=0
        )
        InOrderStatusChange.objects.filter(pk=recent.pk).update(
            created_at=timezone.now() - timedelta(minutes=2)
        )
        expire()
        order.refresh_from_db()
        self.assertEqual(order.status.name, "Expired")
