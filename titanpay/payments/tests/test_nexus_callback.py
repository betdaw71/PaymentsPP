import hashlib
import hmac
import unittest
from unittest.mock import patch

from payments.nexus_client import nexus_map_requisite, verify_nexus_callback


class NexusCallbackSignatureTest(unittest.TestCase):
    def test_docs_control_vector(self):
        secret = "secret"
        callback_id = "42"
        timestamp = "1800000000"
        raw_body = b"{}"
        expected = "v1=3ce7c85276b3fb052e3dd2571481106a67366d4fb9b116d392cf710ebf754cad"
        prefix = f"{callback_id}.{timestamp}.".encode("utf-8")
        digest = hmac.new(secret.encode("utf-8"), prefix + raw_body, hashlib.sha256).hexdigest()
        self.assertEqual(f"v1={digest}", expected)
        with patch("payments.nexus_client.time.time", return_value=1800000000):
            ok = verify_nexus_callback(
                raw_body=raw_body,
                headers={
                    "X-Callback-Id": callback_id,
                    "X-Callback-Timestamp": timestamp,
                    "X-Callback-Signature": expected,
                },
                secret=secret,
            )
        self.assertTrue(ok)

    def test_map_card_requisite(self):
        req = nexus_map_requisite(
            {
                "id": "abc",
                "paymentMethod": "card",
                "paymentDetails": "4400 1234 5678 9012",
                "paymentFullName": "Ivan Ivanov",
                "paymentBank": "Kaspi",
            }
        )
        self.assertEqual(req.get("card_number"), "4400123456789012")
        self.assertEqual(req.get("owner"), "Ivan Ivanov")
        self.assertEqual(req.get("bank"), "Kaspi")
