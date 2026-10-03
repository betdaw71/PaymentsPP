from decimal import Decimal
import inspect

from django.test import SimpleTestCase

from payments.payplat_client import (
    payplat_success_webhook_allows_completed_recalc,
    payplat_webhook_outcome,
    payplat_webhook_paid_amount,
)
from payments.payplat_views import PayplatWebhookView
from payments.psp_payin import parse_psp_webhook_paid_amount


# Реальные IPN по сделке 36ac9db1-b99c-4ca1-8e8e-1a810cbb59b4 (2026-09-23).
FIRST_SUCCESS = {
    "order_id": 273166,
    "shop_internal_id": "36ac9db1-b99c-4ca1-8e8e-1a810cbb59b4",
    "shop_id": 100000100,
    "status": "SUCCESS",
    "invoice": {
        "fiat_amount": "920.14",
        "crypto_amount": "10.47277089",
        "quote_currency": "KZT",
        "quote_amount": "5003.22",
        "quote_rate": "477.73603113",
    },
}

CORRECTED_SUCCESS = {
    "order_id": 273166,
    "shop_internal_id": "36ac9db1-b99c-4ca1-8e8e-1a810cbb59b4",
    "shop_id": 100000100,
    "status": "SUCCESS",
    "invoice": {
        "fiat_amount": "2759.24",
        "crypto_amount": "31.40483242",
        "quote_currency": "KZT",
        "quote_amount": "15003.22",
        "quote_rate": "477.73603113",
    },
}


class PayplatSuccessAmountTest(SimpleTestCase):
    def test_paid_amount_is_quote_not_fiat(self):
        self.assertEqual(payplat_webhook_paid_amount(FIRST_SUCCESS), Decimal("5003.22"))
        self.assertEqual(payplat_webhook_paid_amount(CORRECTED_SUCCESS), Decimal("15003.22"))
        # fiat_amount ≠ quote_amount — нельзя брать fiat
        self.assertNotEqual(
            payplat_webhook_paid_amount(CORRECTED_SUCCESS),
            Decimal(CORRECTED_SUCCESS["invoice"]["fiat_amount"]),
        )
        self.assertEqual(parse_psp_webhook_paid_amount(CORRECTED_SUCCESS), Decimal("15003.22"))

    def test_success_replay_allows_completed_recalc(self):
        self.assertEqual(payplat_webhook_outcome(CORRECTED_SUCCESS), "success")
        self.assertTrue(payplat_success_webhook_allows_completed_recalc(CORRECTED_SUCCESS))

    def test_view_does_not_skip_completed_success(self):
        """Регрессия: раньше Completed → HTTP 200 без apply_psp_completed_recalc."""
        src = inspect.getsource(PayplatWebhookView._handle_success)
        self.assertIn("handle_psp_success_webhook", src)
        self.assertNotIn('name == "Completed"', src)
