from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from payments.dual_fx import (
    expose_usd_amount,
    quote_dual_fx,
)
from payments.merchant_deal_quote import apply_deal_quote, deal_quote_fields
from payments.psp_payin import psp_order_usd_ledger_amount


class _PS:
    def __init__(self, rate, name="C2CKZT", symbol="KZT"):
        self._rate = Decimal(str(rate))
        self.name = name
        self.currency = SimpleNamespace(symbol=symbol)

    def get_rate(self):
        return self._rate


def _trader(username):
    return SimpleNamespace(user=SimpleNamespace(username=username))


@override_settings(
    XE_KZT_MARKUP="1.05",
    XE_KZT_MARKUP_BY_PS="{}",
    PSP_XE_MARKUP_BY_TRADER=(
        '{"payplat1":"1.05","patriot1":"1.03","gipay1":"1.04","visionx1":"1.03",'
        '"layerone1":"1.02","prochub1":"1.02","nexus1":"1.04","plutus1":"1.03"}'
    ),
)
class DualFxQuoteTest(SimpleTestCase):
    def test_gipay_psp_rate_is_xe_plus_4_vs_merchant_plus_5(self):
        ps = _PS("525")
        quote = quote_dual_fx(amount=Decimal("5250"), payment_system=ps, trader=_trader("gipay1"))
        self.assertEqual(quote.merchant_markup, Decimal("1.05"))
        self.assertEqual(quote.psp_markup, Decimal("1.04"))
        self.assertGreater(quote.merchant_rate, quote.psp_rate)
        self.assertGreater(quote.psp_usd, quote.merchant_usd)
        self.assertEqual(quote.merchant_usd, Decimal("10.00"))

    def test_patriot_is_xe_plus_3(self):
        ps = _PS("525")
        quote = quote_dual_fx(amount=Decimal("5250"), payment_system=ps, trader=_trader("patriot1"))
        self.assertEqual(quote.psp_markup, Decimal("1.03"))
        self.assertGreater(quote.merchant_rate, quote.psp_rate)

    def test_payplat_matches_merchant_xe_plus_5(self):
        ps = _PS("525")
        quote = quote_dual_fx(amount=Decimal("5250"), payment_system=ps, trader=_trader("payplat1"))
        self.assertEqual(quote.merchant_rate, quote.psp_rate)

    def test_unknown_psp_matches_merchant(self):
        ps = _PS("525")
        quote = quote_dual_fx(amount=Decimal("5250"), payment_system=ps, trader=_trader("expayone1"))
        self.assertEqual(quote.merchant_rate, quote.psp_rate)
        self.assertEqual(quote.merchant_usd, quote.psp_usd)

    @patch("basics.utils.get_binance_kzt_kaspi_rate", return_value=Decimal("510"))
    def test_bitzone_uses_kaspi_p2p(self, _mock):
        ps = _PS("525")
        quote = quote_dual_fx(amount=Decimal("5250"), payment_system=ps, trader=_trader("bitzone1"))
        self.assertEqual(quote.psp_rate, Decimal("510"))
        self.assertGreater(quote.psp_usd, quote.merchant_usd)

    def test_non_kzt_no_spread(self):
        ps = _PS("92", name="C2C", symbol="RUB")
        quote = quote_dual_fx(amount=Decimal("920"), payment_system=ps, trader=_trader("gipay1"))
        self.assertEqual(quote.merchant_rate, quote.psp_rate)

    def test_expose_psp_hides_merchant_rate(self):
        order = SimpleNamespace(usd_amount=Decimal("10.00"), psp_usd_amount=Decimal("10.12"), merchant_rate=Decimal("525"), psp_rate=Decimal("520"))
        payload = expose_usd_amount(
            {"usd_amount": 10.0, "psp_rate": 520, "merchant_rate": 525, "fx_spread_usd": 0.12},
            order,
            audience="psp",
        )
        self.assertEqual(payload["usd_amount"], 10.12)
        self.assertNotIn("merchant_rate", payload)
        self.assertNotIn("psp_rate", payload)
        self.assertNotIn("fx_spread_usd", payload)

    def test_expose_merchant_hides_psp_rate(self):
        order = SimpleNamespace(usd_amount=Decimal("10.00"), psp_usd_amount=Decimal("10.12"), psp_rate=Decimal("520"))
        payload = expose_usd_amount({"usd_amount": 10.0, "psp_rate": 520, "psp_usd_amount": 10.12}, order, audience="merchant")
        self.assertEqual(payload["usd_amount"], 10.0)
        self.assertNotIn("psp_rate", payload)
        self.assertNotIn("psp_usd_amount", payload)

    def test_ledger_uses_psp_usd(self):
        order = SimpleNamespace(usd_amount=Decimal("10.00"), psp_usd_amount=Decimal("10.12"))
        self.assertEqual(psp_order_usd_ledger_amount(order), Decimal("10.12"))


class DualFxDealQuoteLeakTest(SimpleTestCase):
    def test_aggrepay_quote_never_includes_psp_rate(self):
        user = SimpleNamespace(username="aggrepay")
        merchant = SimpleNamespace(user=user)
        ps = _PS("525")
        order = SimpleNamespace(
            payment_details=None,
            solution=SimpleNamespace(merchant=merchant, mdr_in=Decimal("7.1"), payment_system=ps),
            amount=Decimal("5000"),
            merchant_fee=Decimal("0.75"),
            merchant_rate=Decimal("525"),
            psp_rate=Decimal("520"),
            psp_usd_amount=Decimal("9.62"),
            usd_amount=Decimal("9.52"),
        )
        pay_in = SimpleNamespace(order=order, payment_system=ps, merchant=merchant)
        fields = deal_quote_fields(pay_in)
        self.assertEqual(fields["rate"], 525.0)
        self.assertNotIn("psp_rate", fields)
        data = apply_deal_quote({"usd_amount": 9.52, **fields}, pay_in)
        self.assertNotIn("psp_rate", data)
        self.assertEqual(data["rate"], 525.0)
