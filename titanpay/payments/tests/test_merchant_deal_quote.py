from decimal import Decimal
from unittest import TestCase

from payments.merchant_deal_quote import apply_deal_quote, deal_quote_fields


class _PS:
    def __init__(self, rate):
        self._rate = rate

    def get_rate(self):
        return self._rate


class DealQuoteTest(TestCase):
    def _pay_in(
        self,
        *,
        username="aggrepay",
        rate=Decimal("470.34"),
        mdr=Decimal("7.20"),
        fee=Decimal("0.61"),
        on_pay_in=True,
    ):
        user = type("U", (), {"username": username})()
        merchant = type("M", (), {"user": user})()
        ps = _PS(rate)
        solution = type("S", (), {"merchant": merchant, "mdr_in": mdr, "payment_system": ps})()
        order = type(
            "O",
            (),
            {
                "payment_details": None,
                "solution": solution,
                "amount": Decimal("4002.00"),
                "merchant_fee": fee,
            },
        )()
        return type(
            "P",
            (),
            {
                "order": order,
                "payment_system": ps,
                "merchant": merchant if on_pay_in else None,
            },
        )()

    def test_aggrepay_gets_rate_and_fee(self):
        fields = deal_quote_fields(self._pay_in())
        self.assertEqual(fields["rate"], 470.34)
        self.assertEqual(fields["fee"], 0.61)
        self.assertEqual(fields["fee_percent"], 7.2)

    def test_other_merchant_gets_nothing(self):
        self.assertEqual(deal_quote_fields(self._pay_in(username="melbet")), {})
        data = apply_deal_quote({"usd_amount": 8.5}, self._pay_in(username="mostbet"))
        self.assertEqual(data, {"usd_amount": 8.5})

    def test_username_is_case_insensitive(self):
        self.assertIn("rate", deal_quote_fields(self._pay_in(username="AggrePay")))

    def test_falls_back_to_solution_merchant(self):
        fields = deal_quote_fields(self._pay_in(on_pay_in=False))
        self.assertEqual(fields["fee_percent"], 7.2)

    def test_prefers_group_payment_system_rate(self):
        pay_in = self._pay_in(rate=Decimal("470.34"))
        group_ps = _PS(Decimal("468.00"))
        pay_in.order.payment_details = type(
            "D", (), {"group": type("G", (), {"payment_system": group_ps})()}
        )()
        self.assertEqual(deal_quote_fields(pay_in)["rate"], 468.0)

    def test_no_order(self):
        pay_in = type(
            "P",
            (),
            {"order": None, "merchant": type("M", (), {"user": type("U", (), {"username": "aggrepay"})()})()},
        )()
        self.assertEqual(deal_quote_fields(pay_in), {})
