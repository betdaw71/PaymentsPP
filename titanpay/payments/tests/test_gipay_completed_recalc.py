import inspect
from decimal import Decimal

from django.test import SimpleTestCase

from payments.gipay_client import (
    gipay_success_webhook_allows_completed_recalc,
    gipay_webhook_outcome,
)
from payments.gipay_views import GipayWebhookView
from payments.psp_payin import (
    parse_psp_webhook_paid_amount,
    psp_success_webhook_allows_completed_recalc,
)


GIPAY_FINISHED = {
    "id": "g08e-test-payment",
    "orderId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "state": "finished",
    "currency": "KZT",
    "amount": "5000",
}

GIPAY_FINISHED_CORRECTED = {
    "status": True,
    "result": {
        "id": "g08e-test-payment",
        "orderId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "state": "finished",
        "currency": "KZT",
        "amount": "5004.50",
    },
}


class GipayCompletedRecalcTest(SimpleTestCase):
    def test_finished_is_success(self):
        self.assertEqual(gipay_webhook_outcome(GIPAY_FINISHED), "success")
        self.assertEqual(gipay_webhook_outcome(GIPAY_FINISHED_CORRECTED), "success")

    def test_second_finished_allows_recalc(self):
        self.assertEqual(parse_psp_webhook_paid_amount(GIPAY_FINISHED_CORRECTED), Decimal("5004.50"))
        self.assertTrue(gipay_success_webhook_allows_completed_recalc(GIPAY_FINISHED_CORRECTED))
        self.assertTrue(psp_success_webhook_allows_completed_recalc(GIPAY_FINISHED_CORRECTED))

    def test_view_does_not_skip_completed_success(self):
        src = inspect.getsource(GipayWebhookView._handle_success)
        self.assertIn("handle_psp_success_webhook", src)
        self.assertNotIn('name == "Completed"', src)
