import inspect
from decimal import Decimal

from django.test import SimpleTestCase

from payments.bitzone_client import (
    bitzone_success_webhook_allows_completed_recalc,
    bitzone_webhook_outcome,
)
from payments.bitzone_views import _handle_success as bitzone_handle_success
from payments.psp_payin import (
    parse_psp_webhook_paid_amount,
    psp_success_webhook_allows_completed_recalc,
)
from payments.visionx_client import (
    visionx_success_webhook_allows_completed_recalc,
    visionx_webhook_paid_amount,
    visionx_webhook_outcome,
)
from payments.visionx_views import VisionxWebhookView


BITZONE_CLOSED = {
    "id": "bz-1",
    "status": "closed",
    "fiatAmount": "5000.00",
}

BITZONE_RECALC = {
    "id": "bz-1",
    "status": "re_calculation",
    "fiatAmount": "5000.00",
    "disputeTraderFiatAmount": "5004.50",
}

VISIONX_PAID = {
    "invoice": {
        "id": "vx-1",
        "internalId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "status": "paid",
        "amount": "5000.00",
        "currency": "KZT",
    }
}

VISIONX_PAID_CORRECTED = {
    "invoice": {
        "id": "vx-1",
        "internalId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "status": "paid",
        "amount": "5004.50",
        "currency": "KZT",
    }
}


class BitzoneVisionxCompletedRecalcTest(SimpleTestCase):
    def test_bitzone_recalc_amount_from_dispute_field(self):
        self.assertEqual(bitzone_webhook_outcome(BITZONE_RECALC), "success")
        self.assertEqual(parse_psp_webhook_paid_amount(BITZONE_RECALC), Decimal("5004.50"))
        self.assertTrue(bitzone_success_webhook_allows_completed_recalc(BITZONE_RECALC))
        self.assertTrue(psp_success_webhook_allows_completed_recalc(BITZONE_RECALC))

    def test_bitzone_second_closed_with_new_fiat_allows_recalc(self):
        closed_new = {**BITZONE_CLOSED, "fiatAmount": "5004.50"}
        self.assertEqual(parse_psp_webhook_paid_amount(closed_new), Decimal("5004.50"))
        self.assertTrue(bitzone_success_webhook_allows_completed_recalc(closed_new))

    def test_bitzone_view_does_not_skip_completed(self):
        src = inspect.getsource(bitzone_handle_success)
        self.assertIn("handle_psp_success_webhook", src)
        self.assertNotIn('name == "Completed"', src)

    def test_visionx_paid_amount_from_invoice(self):
        self.assertEqual(visionx_webhook_outcome(VISIONX_PAID), "success")
        self.assertEqual(visionx_webhook_paid_amount(VISIONX_PAID_CORRECTED), Decimal("5004.50"))
        self.assertEqual(parse_psp_webhook_paid_amount(VISIONX_PAID_CORRECTED), Decimal("5004.50"))
        self.assertTrue(visionx_success_webhook_allows_completed_recalc(VISIONX_PAID_CORRECTED))
        self.assertTrue(psp_success_webhook_allows_completed_recalc(VISIONX_PAID_CORRECTED))

    def test_visionx_does_not_eat_bitzone_body(self):
        self.assertIsNone(visionx_webhook_paid_amount(BITZONE_RECALC))
        self.assertEqual(parse_psp_webhook_paid_amount(BITZONE_RECALC), Decimal("5004.50"))

    def test_visionx_view_does_not_skip_completed_success(self):
        src = inspect.getsource(VisionxWebhookView._handle_success)
        self.assertIn("handle_psp_success_webhook", src)
        self.assertNotIn('name == "Completed"', src)
