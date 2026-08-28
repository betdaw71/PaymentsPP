from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from basics.models import Currency, PaymentSystem
from merchant.models import Merchant
from payments.models import Client, PayIn, PayInStatus
from payments.utils2 import check_pending


class CheckPendingPayInTest(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="pending-merchant", password="x")
        merchant = Merchant.objects.create(user=user)
        currency = Currency.objects.create(symbol="KZT", name="Tenge")
        ps = PaymentSystem.objects.create(name="C2CKZT", currency=currency, required_fields={})
        self.client_obj = Client.objects.create(merchant=merchant, client_id="1777606003")
        status = PayInStatus.objects.create(name="In Progress")
        PayIn.objects.create(
            amount=Decimal("15000"),
            currency=currency,
            payment_system=ps,
            merchant_order_id="23199231515",
            callback_url="https://example.com/cb",
            merchant=merchant,
            status=status,
            client=self.client_obj,
        )

    @override_settings(ENFORCE_PENDING_PAYIN=False)
    def test_disabled_allows_second_payin(self):
        self.assertFalse(check_pending(self.client_obj, _in=True))

    @override_settings(ENFORCE_PENDING_PAYIN=True)
    def test_enabled_blocks_second_payin(self):
        self.assertTrue(check_pending(self.client_obj, _in=True))
