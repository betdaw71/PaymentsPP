import inspect
from decimal import Decimal

from django.test import SimpleTestCase

from payments.layerone_client import (
    layerone_success_webhook_allows_completed_recalc,
    layerone_webhook_outcome,
)
from payments.layerone_views import LayeroneWebhookView
from payments.psp_payin import (
    parse_psp_webhook_paid_amount,
    psp_success_webhook_allows_completed_recalc,
)


LAYERONE_FINISHED = {
    "id": "lo-test-payment",
    "orderId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "state": "finished",
    "currency": "KZT",
    "amount": "10000",
}

LAYERONE_FINISHED_CORRECTED = {
    "status": True,
    "result": {
        "id": "lo-test-payment",
        "orderId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "state": "finished",
        "currency": "KZT",
        "amount": "10004.50",
    },
}


class LayeroneCompletedRecalcTest(SimpleTestCase):
    def test_finished_is_success(self):
        self.assertEqual(layerone_webhook_outcome(LAYERONE_FINISHED), "success")
        self.assertEqual(layerone_webhook_outcome(LAYERONE_FINISHED_CORRECTED), "success")

    def test_second_finished_allows_recalc(self):
        self.assertEqual(parse_psp_webhook_paid_amount(LAYERONE_FINISHED_CORRECTED), Decimal("10004.50"))
        self.assertTrue(layerone_success_webhook_allows_completed_recalc(LAYERONE_FINISHED_CORRECTED))
        self.assertTrue(psp_success_webhook_allows_completed_recalc(LAYERONE_FINISHED_CORRECTED))

    def test_view_does_not_skip_completed_success(self):
        src = inspect.getsource(LayeroneWebhookView._handle_success)
        self.assertIn("handle_psp_success_webhook", src)
        self.assertNotIn('name == "Completed"', src)
