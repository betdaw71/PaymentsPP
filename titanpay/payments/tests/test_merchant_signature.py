from django.test import SimpleTestCase

from payments.signing import canonical_json, sign_canonical


ALEMKREDIT_CREATE = {
    "ftd": True,
    "amount": 10800,
    "client": {"client_id": "3929"},
    "currency": "KZT",
    "failed_url": "https://lk.alemcredit.site/account/credits?error",
    "success_url": "https://lk.alemcredit.site/account/credits?success",
    "callback_url": "https://backendalem.com/public/ava-pay/payment-callback",
    "payment_system": "C2CKZT",
    "merchant_order_id": "227_1787936485",
}


class CanonicalSignatureTest(SimpleTestCase):
    def test_create_body_sorts_keys_and_keeps_int_amount(self):
        dumped = canonical_json(ALEMKREDIT_CREATE)
        self.assertTrue(dumped.startswith('{"amount":10800,'))
        self.assertIn('"ftd":true', dumped)
        self.assertNotIn("10800.0", dumped)
        self.assertNotIn("\\/", dumped)
        self.assertNotIn(", ", dumped)

    def test_raw_body_without_sort_differs(self):
        import json

        raw = json.dumps(ALEMKREDIT_CREATE, separators=(",", ":"))
        self.assertNotEqual(raw, canonical_json(ALEMKREDIT_CREATE))

    def test_amount_int_and_float_are_different_payloads(self):
        as_int = canonical_json({"amount": 10800, "status": "Success"})
        as_float = canonical_json({"amount": 10800.0, "status": "Success"})
        self.assertEqual(as_int, '{"amount":10800,"status":"Success"}')
        self.assertEqual(as_float, '{"amount":10800.0,"status":"Success"}')
        self.assertNotEqual(as_int, as_float)

    def test_php_escaped_slashes_would_not_match(self):
        python = canonical_json(ALEMKREDIT_CREATE)
        php_like = python.replace("/", "\\/")
        self.assertNotEqual(python, php_like)

    def test_sign_appends_private_key_with_hyphens(self):
        key = "11111111-2222-4333-8444-555555555555"
        sig, body = sign_canonical({"amount": 10800.0, "status": "Success"}, key)
        import hashlib

        expected = hashlib.sha256((body + key).encode()).hexdigest()
        self.assertEqual(sig, expected)
        self.assertEqual(body, '{"amount":10800.0,"status":"Success"}')


class SignedJsonHeadersTest(SimpleTestCase):
    def test_http_body_bytes_match_signature_input(self):
        import hashlib

        from payments.signing import signed_json_headers

        key = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        payload = {
            "id": "da49359b-f8b0-4c4f-8beb-603f65e57fae",
            "order_id": "227_1787932637",
            "amount": 27000.0,
            "currency": "KZT",
            "payment_system": "C2CKZT",
            "status": "Success",
            "recalculated": False,
            "timestamp": 1787933197,
        }
        headers, body = signed_json_headers(payload, key)
        expected_body = (
            '{"amount":27000.0,"currency":"KZT",'
            '"id":"da49359b-f8b0-4c4f-8beb-603f65e57fae",'
            '"order_id":"227_1787932637","payment_system":"C2CKZT",'
            '"recalculated":false,"status":"Success","timestamp":1787933197}'
        )
        self.assertEqual(body, expected_body.encode())
        self.assertEqual(
            headers["Signature"],
            hashlib.sha256((expected_body + key).encode()).hexdigest(),
        )
