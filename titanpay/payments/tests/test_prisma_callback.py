import hashlib
import hmac
import unittest
from unittest.mock import patch

from payments.prisma_client import (
    prisma_map_requisite,
    prisma_payment_method_for,
    prisma_webhook_outcome,
    verify_prisma_callback,
)


class PrismaCallbackSignatureTest(unittest.TestCase):
    def test_docs_control_vector(self):
        secret = "secret"
        callback_id = "42"
        timestamp = "1800000000"
        raw_body = b"{}"
        expected = "v1=3ce7c85276b3fb052e3dd2571481106a67366d4fb9b116d392cf710ebf754cad"
        prefix = f"{callback_id}.{timestamp}.".encode("utf-8")
        digest = hmac.new(secret.encode("utf-8"), prefix + raw_body, hashlib.sha256).hexdigest()
        self.assertEqual(f"v1={digest}", expected)
        with patch("payments.prisma_client.time.time", return_value=1800000000):
            ok = verify_prisma_callback(
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
        req = prisma_map_requisite(
            {
                "id": "abc",
                "paymentMethod": "card",
                "paymentDetails": "4400 1234 5678 9012",
                "paymentFullName": "Ivan Ivanov",
                "paymentBank": "Optima",
            }
        )
        self.assertEqual(req.get("card_number"), "4400123456789012")
        self.assertEqual(req.get("owner"), "Ivan Ivanov")
        self.assertEqual(req.get("bank"), "Optima")

    def test_map_phone_requisite(self):
        req = prisma_map_requisite(
            {
                "paymentMethod": "phone",
                "paymentDetails": "+996700123456",
                "paymentFullName": "Aibek",
                "paymentBank": "MBank",
            }
        )
        self.assertEqual(req.get("phone"), "+996700123456")
        self.assertEqual(req.get("bank"), "MBank")

    def test_map_qr_requisite(self):
        payload = "000201010212520400005303417..."
        req = prisma_map_requisite(
            {
                "paymentMethod": "qr",
                "paymentDetails": payload,
                "paymentFullName": "QR Owner",
                "paymentBank": "Demir",
            }
        )
        self.assertEqual(req.get("qr_payload"), payload)
        self.assertEqual(req.get("bank"), "Demir")

    def test_kgs_payment_method_map(self):
        self.assertEqual(prisma_payment_method_for("C2CKGS"), "card")
        self.assertEqual(prisma_payment_method_for("PHONEKGS"), "phone")
        self.assertEqual(prisma_payment_method_for("QRKGS"), "qr")

    def test_webhook_outcomes(self):
        self.assertEqual(prisma_webhook_outcome({"status": "SUCCESS"}), "success")
        self.assertEqual(prisma_webhook_outcome({"status": "UPDATED"}), "success")
        self.assertEqual(prisma_webhook_outcome({"status": "EXPIRED"}), "fail")
        self.assertEqual(prisma_webhook_outcome({"status": "NO_REQUISITES"}), "fail")
        self.assertIsNone(prisma_webhook_outcome({"status": "PENDING"}))
