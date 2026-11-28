from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ObjectDoesNotExist
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from payments.merchant_balance import MerchantBalanceView, merchant_balance_payload


class _Addresses:
    def __init__(self, public=None, missing=False):
        self.public = public
        self.missing = missing

    def get(self):
        if self.missing or self.public is None:
            raise ObjectDoesNotExist
        return SimpleNamespace(address_public=self.public)


class _Balance:
    def __init__(self, amount, address=""):
        self.amount = Decimal(amount)
        self.address = _Addresses(address or None, missing=not address)


def _merchant(username="aggrepay", **kwargs):
    user = SimpleNamespace(username=username)
    defaults = dict(
        user=user,
        balance=_Balance("1520.50", "TAddrAggrepay"),
        frozen_balance=_Balance("100.00"),
        balance_kzt=None,
        frozen_balance_kzt=None,
        balance_kgs=None,
        frozen_balance_kgs=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class MerchantBalancePayloadTest(SimpleTestCase):
    def test_usdt_fields_for_regular_merchant(self):
        data = merchant_balance_payload(_merchant())
        self.assertEqual(data["amount"], "1520.50")
        self.assertEqual(data["frozen_amount"], "100.00")
        self.assertEqual(data["currency"], "USDT")
        self.assertEqual(data["deposit_address"], "TAddrAggrepay")
        self.assertNotIn("amount_kzt", data)

    def test_missing_balances_are_zero(self):
        merchant = _merchant()
        merchant.balance = None
        merchant.frozen_balance = None
        data = merchant_balance_payload(merchant)
        self.assertEqual(data["amount"], "0.00")
        self.assertEqual(data["frozen_amount"], "0.00")
        self.assertEqual(data["deposit_address"], "")

    def test_melbet_includes_fiat_ledgers(self):
        merchant = _merchant(
            "melbet",
            balance_kzt=_Balance("10.5"),
            frozen_balance_kzt=_Balance("1"),
            balance_kgs=_Balance("2"),
            frozen_balance_kgs=_Balance("0"),
        )
        data = merchant_balance_payload(merchant)
        self.assertEqual(data["amount_kzt"], "10.50")
        self.assertEqual(data["frozen_amount_kzt"], "1.00")
        self.assertEqual(data["currency_kzt"], "KZT")
        self.assertEqual(data["amount_kgs"], "2.00")
        self.assertEqual(data["frozen_amount_kgs"], "0.00")
        self.assertEqual(data["currency_kgs"], "KGS")


class MerchantBalanceViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_merchant_gets_balance(self):
        merchant = _merchant()
        user = SimpleNamespace(is_superuser=False, is_authenticated=True, merchant=merchant)
        request = self.factory.get("/api/v1/payments/balance/")
        force_authenticate(request, user=user)
        response = MerchantBalanceView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["amount"], "1520.50")
        self.assertEqual(response.data["currency"], "USDT")

    def test_admin_without_merchant_is_forbidden(self):
        user = SimpleNamespace(is_superuser=True, is_authenticated=True)
        request = self.factory.get("/api/v1/payments/balance/")
        force_authenticate(request, user=user)
        response = MerchantBalanceView.as_view()(request)
        self.assertEqual(response.status_code, 403)
