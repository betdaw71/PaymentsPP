from decimal import Decimal
from unittest import TestCase

from rest_framework.exceptions import ValidationError

from payments.merchant_deal_quote import callback_extra_fields, deal_quote_fields
from payments.merchant_usd_amount import apply_usd_amount_flag, is_alemkredit_merchant


class _PS:
    def __init__(self, rate):
        self._rate = rate

    def get_rate(self):
        return self._rate


def _merchant(username="alemkredit"):
    user = type("U", (), {"username": username})()
    return type("M", (), {"user": user})()


class UsdAmountFlagTest(TestCase):
    def test_converts_usd_to_kzt_for_alemkredit(self):
        merchant = _merchant()
        data = {
            "amount": Decimal("10"),
            "amount_in_usd": True,
            "payment_system": _PS(Decimal("470.34")),
        }
        fiat = apply_usd_amount_flag(data, merchant)
        self.assertEqual(fiat, Decimal("4703.40"))
        self.assertEqual(data["amount"], Decimal("4703.40"))
        self.assertNotIn("amount_in_usd", data)

    def test_other_merchant_cannot_use_flag(self):
        data = {
            "amount": Decimal("10"),
            "amount_in_usd": True,
            "payment_system": _PS(Decimal("470.34")),
        }
        with self.assertRaises(ValidationError):
            apply_usd_amount_flag(data, _merchant("aggrepay"))

    def test_without_flag_keeps_fiat_amount(self):
        data = {"amount": Decimal("5000"), "payment_system": _PS(Decimal("470.34"))}
        self.assertEqual(apply_usd_amount_flag(data, _merchant()), Decimal("5000"))

    def test_username_is_case_insensitive(self):
        self.assertTrue(is_alemkredit_merchant(_merchant("AlemKredit")))


class AlemkreditQuoteTest(TestCase):
    def _pay_in(self, username="alemkredit", rate=Decimal("470.34")):
        user = type("U", (), {"username": username})()
        merchant = type("M", (), {"user": user})()
        ps = _PS(rate)
        order = type(
            "O",
            (),
            {
                "payment_details": None,
                "solution": type("S", (), {"merchant": merchant, "payment_system": ps})(),
                "amount": Decimal("4703.40"),
            },
        )()
        return type("P", (), {"order": order, "payment_system": ps, "merchant": merchant})()

    def test_create_and_callback_include_rate(self):
        pay_in = self._pay_in()
        self.assertEqual(deal_quote_fields(pay_in), {"rate": 470.34})
        self.assertEqual(callback_extra_fields(pay_in), {"rate": 470.34})

    def test_other_merchant_callback_has_no_rate(self):
        pay_in = self._pay_in(username="aggrepay")
        self.assertNotIn("rate", callback_extra_fields(pay_in) or {"rate": None})
        self.assertEqual(callback_extra_fields(pay_in), {})
