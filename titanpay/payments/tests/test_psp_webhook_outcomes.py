from django.test import SimpleTestCase

from payments.aggrepay_webhook import webhook_ids, webhook_outcome, webhook_state
from payments.gipay_client import gipay_webhook_outcome
from payments.layerone_client import layerone_webhook_outcome
from payments.plutus_client import _plutus_webhook_lookup_values, plutus_webhook_outcome
from payments.patriotpay_client import patriotpay_webhook_outcome


class AggrepayWebhookHelpersTest(SimpleTestCase):
    def test_nested_result_finished_is_success(self):
        body = {
            "status": True,
            "result": {
                "id": "g08eabc",
                "orderId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "state": "finished",
            },
        }
        self.assertEqual(webhook_outcome(body), "success")
        self.assertEqual(webhook_state(body), "finished")
        order_id, payment_id = webhook_ids(body)
        self.assertEqual(order_id, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(payment_id, "g08eabc")
        self.assertEqual(gipay_webhook_outcome(body), "success")
        self.assertEqual(layerone_webhook_outcome(body), "success")

    def test_create_envelope_is_ignored(self):
        body = {"status": True, "result": {"state": "created", "orderId": "x"}}
        self.assertIsNone(webhook_outcome(body))
        self.assertIsNone(gipay_webhook_outcome(body))

    def test_paid_and_snake_case_order_id(self):
        body = {"order_id": "oid-1", "payment_id": "pid-1", "state": "paid"}
        self.assertEqual(webhook_outcome(body), "success")
        self.assertEqual(webhook_ids(body), ("oid-1", "pid-1"))

    def test_boolean_status_alone_is_not_success(self):
        self.assertIsNone(webhook_outcome({"status": True}))


class PlutusWebhookHelpersTest(SimpleTestCase):
    def test_completed_and_success_are_paid(self):
        self.assertEqual(plutus_webhook_outcome({"status": "completed"}), "success")
        self.assertEqual(plutus_webhook_outcome({"status": "success"}), "success")
        self.assertEqual(plutus_webhook_outcome({"status": "paid"}), "success")

    def test_lookup_values_include_id_and_trade(self):
        values = _plutus_webhook_lookup_values(
            {"id": "our-id", "platform": {"trade_id": "trade-1"}}
        )
        self.assertIn("our-id", values)
        self.assertIn("trade-1", values)


class PatriotpayWebhookStatusTest(SimpleTestCase):
    def test_success_alias_is_paid(self):
        self.assertEqual(patriotpay_webhook_outcome({"status": "success"}), "success")
        self.assertEqual(patriotpay_webhook_outcome({"status": "completed"}), "success")
