from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from basics.models import Currency, PaymentSystem
from merchant.models import Merchant
from payments.payout_remap import remap_payout_payment_system_id
from payments.rate_views import PayoutKztRateView


class PayoutKztRateViewTest(TestCase):
    def setUp(self):
        self.kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        PaymentSystem.objects.create(
            name="C2CKZT",
            currency=self.kzt,
            required_fields={},
            usdt_exchange_rate=Decimal("540.00"),
            last_update=1700000000,
            in_on=True,
            out_on=True,
        )
        self.ps = PaymentSystem.objects.create(
            name="PAYOUTKZT",
            currency=self.kzt,
            required_fields={},
            usdt_exchange_rate=Decimal("468.50"),
            last_update=1700000000,
            in_on=False,
            out_on=False,
        )
        self.factory = APIRequestFactory()

    def test_returns_bybit_payoutkzt_not_c2ckzt_xe(self):
        request = self.factory.get("/api/v1/payments/rate/payoutkzt/")
        response = PayoutKztRateView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rate"], "468.50")
        self.assertEqual(response.data["payment_system"], "PAYOUTKZT")
        self.assertEqual(response.data["source"], "bybit_kaspi")
        self.assertEqual(response.data["method"]["payment"], "Kaspi")
        self.assertEqual(response.data["method"]["rows"], [15, 16])
        self.assertNotEqual(response.data["rate"], "540.00")

    @override_settings(RATE_API_TOKEN="secret-rate")
    def test_token_required_when_configured(self):
        request = self.factory.get("/api/v1/payments/rate/payoutkzt/")
        response = PayoutKztRateView.as_view()(request)
        self.assertEqual(response.status_code, 403)
        request = self.factory.get("/api/v1/payments/rate/payoutkzt/", HTTP_X_RATE_TOKEN="secret-rate")
        response = PayoutKztRateView.as_view()(request)
        self.assertEqual(response.status_code, 200)


class PayoutC2cRemapTest(TestCase):
    def setUp(self):
        self.kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        self.c2c = PaymentSystem.objects.create(
            name="C2C", currency=self.kzt, required_fields={}, usdt_exchange_rate=Decimal("500")
        )
        self.c2ckzt = PaymentSystem.objects.create(
            name="C2CKZT", currency=self.kzt, required_fields={}, usdt_exchange_rate=Decimal("500")
        )
        mu = User.objects.create_user(username="mostbet", password="x")
        self.merchant = Merchant.objects.create(user=mu)
        other = User.objects.create_user(username="pandapay", password="x")
        self.other = Merchant.objects.create(user=other)

    @override_settings(PAYOUT_C2C_TO_C2CKZT_MERCHANTS="mostbet")
    def test_mostbet_c2c_kzt_becomes_c2ckzt(self):
        data = {"payment_system": self.c2c.id, "currency": self.kzt.id}
        mapped = remap_payout_payment_system_id(data, self.merchant)
        self.assertEqual(mapped["payment_system"], self.c2ckzt.id)

    @override_settings(PAYOUT_C2C_TO_C2CKZT_MERCHANTS="mostbet")
    def test_other_merchant_keeps_c2c(self):
        data = {"payment_system": self.c2c.id}
        mapped = remap_payout_payment_system_id(data, self.other)
        self.assertEqual(mapped["payment_system"], self.c2c.id)

    @override_settings(PAYOUT_C2C_TO_C2CKZT_MERCHANTS="mostbet")
    def test_already_c2ckzt_unchanged(self):
        data = {"payment_system": self.c2ckzt.id}
        mapped = remap_payout_payment_system_id(data, self.merchant)
        self.assertEqual(mapped["payment_system"], self.c2ckzt.id)
