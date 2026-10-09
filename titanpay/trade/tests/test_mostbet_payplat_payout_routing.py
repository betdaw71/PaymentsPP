from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

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
from merchant.models import Merchant
from trade.utils import choose_trader_out


@override_settings(
    PAYOUT_PREFERRED_TRADER_BY_MERCHANT='{"mostbet":"payplat1"}',
    PAYPLAT_TRADER_USERNAME="payplat1",
    MELBET_KZT_TEST_TRADER_USERNAME="",
    KZT_C2C_BANK_PS_NAMES="Vietcombank",
)
class MostbetPayplatPayoutRoutingTest(TestCase):
    def setUp(self):
        self.kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        self.traffic = TrafficType.objects.create(name="Standard")
        fields = {"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}}
        self.c2ckzt = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=self.kzt,
            required_fields=fields,
            usdt_exchange_rate=Decimal("500"),
        )
        self.vcb = PaymentSystem.objects.create(
            name="Vietcombank",
            currency=self.kzt,
            required_fields=fields,
            usdt_exchange_rate=Decimal("480"),
        )
        self.team = TraderTeam.objects.create(name="kzt-out")
        mu = User.objects.create_user(username="mostbet", password="x")
        self.merchant = Merchant.objects.create(
            user=mu,
            balance=Balance.objects.create(type=0, amount=Decimal("100000")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.payplat_group = self._out_group("payplat1", self.c2ckzt, Decimal("90000"))
        self.vcb_group = self._out_group("vndk_out", self.vcb, Decimal("0"))

    def _out_group(self, username, ps, volume):
        user = User.objects.create_user(username=username, password="x")
        trader = Trader.objects.create(
            user=user,
            team=self.team,
            currency=self.kzt,
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("100000")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        group = PaymentDetailsGroup.objects.create(
            trader=trader,
            currency=self.kzt,
            payment_system=ps,
            status=1,
            out_active=True,
            in_active=False,
            amount=Decimal("9999999"),
            min_amount_out=Decimal("1000"),
            max_amount_out=Decimal("5000000"),
            work_type="by_card",
            deposit_number_on=False,
            current_out_volume=volume,
            owner=username,
        )
        group.allowed_traffic.add(self.traffic)
        digits = f"{uuid4().int:040d}"
        PaymentDetails.objects.create(
            group=group,
            status=1,
            card_number=digits[:16],
            deposit_number=digits[16:36],
            sberpay_enabled=False,
            sbp_enabled=False,
        )
        return group

    def test_mostbet_c2ckzt_picks_payplat_over_lower_volume_bank(self):
        detail, _usd, ok = choose_trader_out(
            Decimal("20000"), self.c2ckzt, self.traffic, merchant=self.merchant
        )
        self.assertTrue(ok)
        self.assertEqual(detail.group.trader.user.username, "payplat1")
