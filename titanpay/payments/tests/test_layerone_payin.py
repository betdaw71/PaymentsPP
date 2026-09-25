from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from payments.layerone_client import (
    layerone_callback_url,
    layerone_create_payment,
    layerone_map_requisite,
    layerone_payin_method_for,
    layerone_webhook_outcome,
    verify_webhook_signature,
)


class LayeronePayinHelpersTest(SimpleTestCase):
    @override_settings(LAYERONE_PAYIN_METHOD="tgkz", LAYERONE_PAYIN_METHOD_MAP='{"C2CKZT":"tgkz","C2C":"tgkz"}')
    def test_method_is_tgkz_for_c2ckzt(self):
        self.assertEqual(layerone_payin_method_for("C2CKZT"), "tgkz")
        self.assertEqual(layerone_payin_method_for("C2C"), "tgkz")

    def test_finished_is_success(self):
        self.assertEqual(layerone_webhook_outcome({"state": "finished"}), "success")

    def test_expired_is_fail(self):
        self.assertEqual(layerone_webhook_outcome({"state": "expired"}), "fail")

    def test_created_is_ignored(self):
        self.assertIsNone(layerone_webhook_outcome({"state": "created"}))

    def test_map_card_requisite(self):
        req = layerone_map_requisite(
            {"result": {"address": "4400430182839016", "recipient": "IVAN", "bankName": "Kaspi"}}
        )
        self.assertEqual(req["card_number"], "4400430182839016")
        self.assertEqual(req["owner"], "IVAN")
        self.assertEqual(req["bank"], "Kaspi")

    @override_settings(
        LAYERONE_API_BASE="https://layer-1.io",
        LAYERONE_API_KEY="1|token",
        LAYERONE_MERCHANT_ID="mid",
        LAYERONE_SECRET_KEY="secret",
        LAYERONE_PAYIN_METHOD="tgkz",
    )
    @patch("payments.layerone_client._request", return_value=(True, {"result": {"id": "p1", "state": "created"}}))
    def test_create_sends_tgkz_and_kzt(self, req):
        ok, data = layerone_create_payment(
            amount=Decimal("20000"),
            order_id="po-1",
            currency="KZT",
            method="tgkz",
        )
        self.assertTrue(ok)
        payload = req.call_args.kwargs["json_payload"]
        self.assertEqual(payload["method"], "tgkz")
        self.assertEqual(payload["currency"], "KZT")
        self.assertEqual(payload["amount"], "20000")
        self.assertEqual(payload["merchantId"], "mid")
        self.assertEqual(req.call_args.args[:2], ("POST", "/api/v2/payments"))

    @override_settings(PUBLIC_API_URL="https://api.avapay.net")
    def test_callback_url(self):
        self.assertEqual(layerone_callback_url(), "https://api.avapay.net/api/v1/webhooks/psp/layerone/")

    @override_settings(LAYERONE_SECRET_KEY="secret", LAYERONE_API_KEY="1|token", LAYERONE_WEBHOOK_SKIP_VERIFY=False)
    def test_webhook_signature_hmac(self):
        import hashlib
        import hmac

        raw = b'{"orderId":"x","state":"finished"}'
        sig = hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(raw, sig))
        self.assertFalse(verify_webhook_signature(raw, "deadbeef"))
