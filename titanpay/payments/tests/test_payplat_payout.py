from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from payments.payplat_client import (
    payplat_create_payout,
    payplat_is_payout_webhook,
    payplat_payout_create_rejected,
    payplat_webhook_outcome,
    _payout_amount_for_payplat,
)


class PayplatPayoutHelpersTest(SimpleTestCase):
    def test_payout_ipn_paid_is_success(self):
        body = {"type": "PAYOUT", "status": "PAID", "shop_internal_id": "abc"}
        self.assertTrue(payplat_is_payout_webhook(body))
        self.assertEqual(payplat_webhook_outcome(body), "success")

    def test_payout_ipn_cancelled_is_fail(self):
        body = {"type": "payout", "status": "CANCELLED"}
        self.assertEqual(payplat_webhook_outcome(body), "fail")

    def test_payout_ipn_amount_below_minimum_is_fail(self):
        body = {"type": "PAYOUT", "status": "amount_below_minimum"}
        self.assertEqual(payplat_webhook_outcome(body), "fail")

    def test_payout_ipn_insufficient_balance_is_fail(self):
        body = {"type": "PAYOUT", "status": "insufficient_merchant_balance"}
        self.assertEqual(payplat_webhook_outcome(body), "fail")

    def test_create_amount_below_minimum_is_rejected(self):
        self.assertTrue(
            payplat_payout_create_rejected({"status": "amount_below_minimum", "order_id": 1})
        )
        self.assertTrue(
            payplat_payout_create_rejected({"status": "insufficient_merchant_balance", "order_id": 1})
        )
        self.assertFalse(payplat_payout_create_rejected({"status": "WAITING", "order_id": 1}))

    def test_payin_success_unchanged(self):
        body = {"status": "SUCCESS", "shop_internal_id": "abc"}
        self.assertFalse(payplat_is_payout_webhook(body))
        self.assertEqual(payplat_webhook_outcome(body), "success")

    @override_settings(PAYPLAT_PAYOUT_CURRENCY="KZT")
    def test_amount_uses_kzt_when_currency_kzt(self):
        pay_out = type(
            "P",
            (),
            {"amount": Decimal("50000"), "order": type("O", (), {"usd_amount": Decimal("106.47")})()},
        )()
        self.assertEqual(_payout_amount_for_payplat(pay_out), Decimal("50000"))

    @override_settings(PAYPLAT_PAYOUT_CURRENCY="", PAYPLAT_PAYOUT_AMOUNT_MODE="usd")
    @patch("payments.payoutkzt_rate.get_payoutkzt_rate", return_value=Decimal("500"))
    def test_amount_uses_payoutkzt_bybit_rate(self, _rate):
        pay_out = type(
            "P",
            (),
            {"amount": Decimal("20000"), "order": type("O", (), {"usd_amount": Decimal("41.23")})()},
        )()
        self.assertEqual(_payout_amount_for_payplat(pay_out), Decimal("40.00"))

    @override_settings(PAYPLAT_PAYOUT_CURRENCY="", PAYPLAT_PAYOUT_AMOUNT_MODE="usd")
    @patch("payments.payoutkzt_rate.get_payoutkzt_rate", return_value=None)
    def test_amount_falls_back_to_order_usd_without_payoutkzt(self, _rate):
        pay_out = type(
            "P",
            (),
            {"amount": Decimal("20000"), "id": "x", "order": type("O", (), {"usd_amount": Decimal("41.23")})()},
        )()
        self.assertEqual(_payout_amount_for_payplat(pay_out), Decimal("41.23"))

    @override_settings(PAYPLAT_PAYOUT_CURRENCY="", PAYPLAT_PAYOUT_AMOUNT_MODE="fiat")
    def test_amount_fiat_mode_uses_kzt(self):
        pay_out = type("P", (), {"amount": Decimal("20000"), "order": type("O", (), {"usd_amount": Decimal("41.23")})()})()
        self.assertEqual(_payout_amount_for_payplat(pay_out), Decimal("20000"))

    @override_settings(
        PAYPLAT_SHOP_ID="100000100",
        PAYPLAT_SECRET_KEY="secret",
        PAYPLAT_API_BASE="https://payplat.su/test/api",
        PAYPLAT_PAYOUT_REQUISITE_TYPE="card",
        PAYPLAT_PAYOUT_TYPE="kzt",
        PAYPLAT_PAYOUT_CURRENCY="KZT",
        PAYPLAT_PAYOUT_NAME="IVAN",
        PAYPLAT_PAYOUT_SURNAME="PETROV",
        PAYPLAT_PAYOUT_BANK="kaspi",
        PAYPLAT_TARIFF="PRIMARY",
    )
    @patch("payments.payplat_client._request", return_value=(True, {"payout_id": "p1", "status": "WAITING"}))
    def test_create_payout_sends_kzt_currency(self, req):
        ok, data = payplat_create_payout(
            amount=Decimal("50000"),
            shop_internal_id="po-1",
            card_number="4111111111111111",
            bank="kaspi",
            name="IVAN",
            surname="PETROV",
        )
        self.assertTrue(ok)
        self.assertEqual(data["payout_id"], "p1")
        method, path = req.call_args.args[:2]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/payout")
        payload = req.call_args.kwargs["json_payload"]
        self.assertEqual(payload["amount"], 50000)
        self.assertEqual(payload["currency"], "KZT")
        self.assertEqual(payload["payout_type"], "kzt")
        self.assertEqual(payload["card_number"], "4111111111111111")
        self.assertEqual(payload["requisite_type"], "card")
        self.assertEqual(payload["bank"], "kaspi")
        self.assertEqual(payload["name"], "IVAN")
        self.assertEqual(payload["surname"], "PETROV")
        self.assertEqual(payload["shop_internal_id"], "po-1")
        self.assertEqual(payload["tariff"], "PRIMARY")
