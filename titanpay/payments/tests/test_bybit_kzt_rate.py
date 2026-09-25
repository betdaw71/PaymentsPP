from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from basics.utils import get_bybit_kzt_rate, get_bybit_kzt_rate_quote


def _item(price, payments=None):
    return {"price": str(price), "payments": payments if payments is not None else ["150"]}


class BybitKztRateTest(SimpleTestCase):
    def _response(self, items):
        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ret_code": 0, "result": {"items": items}}

        return _Resp()

    @override_settings(BYBIT_KZT_AMOUNT="50000", BYBIT_KZT_AUTH_MAKER=True, BYBIT_KZT_ROWS="15,16")
    @patch("basics.utils.requests.post")
    def test_average_of_rows_15_and_16_in_book_order(self, post):
        items = [_item(i) for i in range(1, 21)]
        post.return_value = self._response(items)
        quote = get_bybit_kzt_rate_quote()
        self.assertIsNotNone(quote)
        self.assertEqual(quote["rate"], Decimal("15.50"))
        self.assertEqual(quote["rows"], [15, 16])
        self.assertEqual(quote["prices"], [Decimal("15"), Decimal("16")])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["amount"], "50000")
        self.assertEqual(payload["payment"], ["150"])
        self.assertEqual(payload["side"], "1")
        self.assertTrue(payload["authMaker"])

    @override_settings(BYBIT_KZT_ROWS="15,16")
    @patch("basics.utils.requests.post")
    def test_skips_non_kaspi_then_uses_display_rows(self, post):
        items = [_item(99, payments=["1"])] + [_item(i) for i in range(1, 17)]
        post.return_value = self._response(items)
        rate = get_bybit_kzt_rate()
        self.assertEqual(rate, Decimal("15.50"))

    @override_settings(BYBIT_KZT_ROWS="15,16")
    @patch("basics.utils.requests.post")
    def test_fallback_last_rows_when_book_is_short(self, post):
        items = [_item(10), _item(20), _item(30)]
        post.return_value = self._response(items)
        quote = get_bybit_kzt_rate_quote()
        self.assertEqual(quote["rate"], Decimal("25.00"))
        self.assertEqual(quote["prices"], [Decimal("20"), Decimal("30")])
