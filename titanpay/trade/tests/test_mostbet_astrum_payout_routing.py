from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError

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
from trade.utils import check_details, choose_trader_out


@override_settings(
    PAYOUT_PREFERRED_TRADER_BY_MERCHANT='{"mostbet":"astrum_kzt"}',
    ASTRUM_TRADER_USERNAME="astrum_kzt",
    MELBET_KZT_TEST_TRADER_USERNAME="",
    KZT_C2C_BANK_PS_NAMES="Vietcombank",
)
class MostbetAstrumPayoutRoutingTest(TestCase):
    def setUp(self):
        self.kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        self.traffic = TrafficType.objects.create(name="Standard")
        self.other_traffic = TrafficType.objects.create(name="Gamble")
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
        self.astrum_group = self._out_group("astrum_kzt", self.c2ckzt, Decimal("90000"))
        self.vcb_group = self._out_group("vndk_out", self.vcb, Decimal("0"))

    def _out_group(self, username, ps, volume, traffic=None):
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
        group.allowed_traffic.add(traffic if traffic is not None else self.traffic)
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

    def test_mostbet_c2ckzt_picks_astrum_over_lower_volume_bank(self):
        detail, _usd, ok = choose_trader_out(
            Decimal("20000"), self.c2ckzt, self.traffic, merchant=self.merchant
        )
        self.assertTrue(ok)
        self.assertEqual(detail.group.trader.user.username, "astrum_kzt")

    def test_without_merchant_bank_with_lower_volume_wins(self):
        detail, _usd, ok = choose_trader_out(
            Decimal("20000"), self.c2ckzt, self.traffic, merchant=None
        )
        self.assertTrue(ok)
        self.assertEqual(detail.group.trader.user.username, "vndk_out")

    def test_astrum_psp_out_ignores_traffic_mismatch(self):
        self.astrum_group.allowed_traffic.clear()
        self.astrum_group.allowed_traffic.add(self.other_traffic)
        detail, _usd, ok = choose_trader_out(
            Decimal("20000"), self.c2ckzt, self.traffic, merchant=self.merchant
        )
        self.assertTrue(ok)
        self.assertEqual(detail.group.trader.user.username, "astrum_kzt")

    def test_check_details_ignores_extra_recipient_name(self):
        self.assertTrue(
            check_details(
                self.c2ckzt,
                {"card_number": "4111111111111111", "recipient_name": "IVAN IVANOV"},
            )
        )

    def test_check_details_still_requires_card_number(self):
        with self.assertRaises(ValidationError):
            check_details(self.c2ckzt, {"recipient_name": "IVAN IVANOV"})
