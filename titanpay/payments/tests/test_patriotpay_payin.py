from decimal import Decimal
from unittest.mock import patch
import inspect

from django.test import SimpleTestCase, override_settings

from payments.patriotpay_client import (
    _sign_request,
    patriotpay_callback_url,
    patriotpay_create_invoice,
    patriotpay_map_requisite,
    patriotpay_payment_option_for,
    patriotpay_webhook_outcome,
    patriotpay_webhook_paid_amount,
    patriotpay_success_webhook_allows_completed_recalc,
    verify_webhook_token,
)
from payments.patriotpay_views import PatriotpayWebhookView
from payments.psp_payin import parse_psp_webhook_paid_amount, psp_success_webhook_allows_completed_recalc


class PatriotpayPayinHelpersTest(SimpleTestCase):
    @override_settings(
        PATRIOTPAY_PAYIN_OPTION="TO_CARD",
        PATRIOTPAY_PAYIN_OPTION_MAP='{"C2CKZT":"TO_CARD","C2C":"TO_CARD"}',
    )
    def test_option_is_to_card_for_c2ckzt(self):
        self.assertEqual(patriotpay_payment_option_for("C2CKZT"), "TO_CARD")
        self.assertEqual(patriotpay_payment_option_for("C2C"), "TO_CARD")

    def test_paid_is_success(self):
        self.assertEqual(patriotpay_webhook_outcome({"status": "paid"}), "success")
        self.assertEqual(patriotpay_webhook_outcome({"invoice": {"status": "paid"}}), "success")

    def test_expired_is_fail(self):
        self.assertEqual(patriotpay_webhook_outcome({"status": "expired"}), "fail")
        self.assertEqual(patriotpay_webhook_outcome({"status": "canceled"}), "fail")

    def test_new_is_ignored(self):
        self.assertIsNone(patriotpay_webhook_outcome({"status": "new"}))

    def test_paid_amount_from_sum(self):
        body = {
            "invoice": {
                "id": "inv-1",
                "internalId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "status": "paid",
                "sum": {"amount": "5004.50", "currency": "KZT", "subunit": 2},
            }
        }
        self.assertEqual(patriotpay_webhook_paid_amount(body), Decimal("5004.50"))
        self.assertTrue(patriotpay_success_webhook_allows_completed_recalc(body))
        self.assertEqual(parse_psp_webhook_paid_amount(body), Decimal("5004.50"))
        self.assertTrue(psp_success_webhook_allows_completed_recalc(body))

    def test_view_does_not_skip_completed_success(self):
        src = inspect.getsource(PatriotpayWebhookView._handle_success)
        self.assertIn("handle_psp_success_webhook", src)
        self.assertNotIn('name == "Completed"', src)

    def test_map_card_requisite(self):
        req = patriotpay_map_requisite(
            {
                "deals": [
                    {
                        "paymentMethod": "kaspi",
                        "paymentOption": "TO_CARD",
                        "requisites": {"requisites": "4400 4301 8283 9016", "holder": "IVAN"},
                    }
                ]
            }
        )
        self.assertEqual(req["card_number"], "4400430182839016")
        self.assertEqual(req["owner"], "IVAN")
        self.assertEqual(req["bank"], "kaspi")

    def test_map_phone_requisite(self):
        req = patriotpay_map_requisite(
            {
                "deals": [
                    {
                        "paymentMethod": "kaspi",
                        "paymentOption": "TO_PHONE_NUMBER",
                        "requisites": {"requisites": "77001234567", "holder": "IVAN"},
                    }
                ]
            }
        )
        self.assertEqual(req["phone"], "+77001234567")

    @override_settings(
        PATRIOTPAY_API_BASE="https://api.patriotpay.club",
        PATRIOTPAY_API_KEY="api-key",
        PATRIOTPAY_SECRET_KEY="secret",
        PATRIOTPAY_PAYIN_OPTION="TO_CARD",
    )
    @patch(
        "payments.patriotpay_client._request",
        return_value=(True, {"id": "inv-1", "deals": [{"id": "deal-1"}]}),
    )
    def test_create_sends_to_card_and_kzt(self, req):
        ok, data = patriotpay_create_invoice(
            amount=Decimal("20000"),
            internal_id="po-1",
            currency="KZT",
            notification_url="https://api.avapay.net/api/v1/webhooks/psp/patriotpay/",
            notification_token="tok",
            payment_option="TO_CARD",
        )
        self.assertTrue(ok)
        payload = req.call_args.kwargs["json_payload"]
        self.assertEqual(payload["type"], "in")
        self.assertEqual(payload["currency"], "KZT")
        self.assertEqual(payload["amount"], "20000")
        self.assertEqual(payload["paymentOption"], "TO_CARD")
        self.assertTrue(payload["startDeal"])
        self.assertEqual(req.call_args.args[:2], ("POST", "/api/merchant/invoices"))

    @override_settings(PUBLIC_API_URL="https://api.avapay.net")
    def test_callback_url(self):
        self.assertEqual(patriotpay_callback_url(), "https://api.avapay.net/api/v1/webhooks/psp/patriotpay/")

    @override_settings(PATRIOTPAY_SECRET_KEY="secret", PATRIOTPAY_WEBHOOK_SKIP_VERIFY=False)
    def test_webhook_token(self):
        self.assertTrue(verify_webhook_token("abc", "abc"))
        self.assertFalse(verify_webhook_token("abc", "xyz"))
        self.assertFalse(verify_webhook_token("", "abc"))

    @override_settings(PATRIOTPAY_SECRET_KEY="secret")
    def test_hmac_sha1_signature(self):
        import base64
        import hashlib
        import hmac

        body = '{"amount":"1000"}'
        url = "https://api.patriotpay.club/api/merchant/invoices"
        expected = base64.b64encode(
            hmac.new(b"secret", f"POST{url}{body}".encode("utf-8"), hashlib.sha1).digest()
        ).decode("ascii")
        self.assertEqual(_sign_request(method="POST", url=url, body=body), expected)
