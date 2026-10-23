from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from payments.payplat_client import (
    payplat_create_deal,
    payplat_deal_currency,
    payplat_map_requisite,
    payplat_payer_for,
    payplat_requisite_matches_requested_type,
    payplat_requisite_type_for,
    payplat_webhook_paid_amount,
)
from payments.integrations.melbet.mapping import resolve_method_entry


class _Cfg:
    def __init__(self, method_map):
        self.method_map = method_map


class PayplatLkqTest(SimpleTestCase):
    def test_qrkgs_requisite_type_is_lkq_without_env_map(self):
        self.assertEqual(payplat_requisite_type_for("QRKGS"), "lkq")

    def test_kgs_does_not_inherit_default_kz_payer(self):
        pay_in = type("P", (), {"currency": type("C", (), {"symbol": "KGS"})()})()
        self.assertIsNone(payplat_payer_for("QRKGS", pay_in))
        self.assertIsNone(payplat_payer_for(None, pay_in))

    def test_kzt_still_gets_kz_payer(self):
        pay_in = type("P", (), {"currency": type("C", (), {"symbol": "KZT"})()})()
        self.assertEqual(payplat_payer_for("C2CKZT", pay_in), "kz")

    def test_deal_currency_kgs_is_lowercase(self):
        pay_in = type(
            "P",
            (),
            {
                "currency": type("C", (), {"symbol": "KGS"})(),
                "payment_system": type("S", (), {"name": "QRKGS"})(),
            },
        )()
        self.assertEqual(payplat_deal_currency(pay_in), "kgs")
        self.assertIsNone(
            payplat_deal_currency(
                type(
                    "P",
                    (),
                    {
                        "currency": type("C", (), {"symbol": "KZT"})(),
                        "payment_system": type("S", (), {"name": "C2CKZT"})(),
                    },
                )()
            )
        )

    def test_map_widget_url(self):
        req = payplat_map_requisite(
            {
                "widget_url": "https://payplat.example/widget/abc",
                "requisite": {"bank": "MBK"},
            }
        )
        self.assertEqual(req["payment_form_url"], "https://payplat.example/widget/abc")
        self.assertEqual(req["bank"], "MBK")

    def test_h2h_card_still_maps(self):
        req = payplat_map_requisite({"requisite": {"card_number": "4000000000000001", "holder_name": "IVAN"}})
        self.assertEqual(req["card_number"], "4000000000000001")

    def test_transborder_card_wins_over_qr_url(self):
        req = payplat_map_requisite(
            {
                "qr_url": "https://qrnspk.ru/h/abc",
                "requisite": {
                    "card_number": "4154795018971797",
                    "holder_name": "IVAN",
                    "bank": "tbcbank_ge",
                },
            }
        )
        self.assertEqual(req["card_number"], "4154795018971797")
        self.assertNotIn("payment_form_url", req)

    def test_kgs_usdt_quote_is_not_paid_fiat(self):
        body = {
            "shop_internal_id": "x",
            "status": "SUCCESS",
            "amount": "1500",
            "invoice": {
                "fiat_amount": "1500",
                "quote_currency": "USDT",
                "quote_amount": "17.24",
                "quote_rate": "87.01",
            },
        }
        self.assertEqual(payplat_webhook_paid_amount(body), Decimal("1500"))

    @override_settings(PAYPLAT_SHOP_ID="1", PAYPLAT_SECRET_KEY="s")
    def test_create_deal_sends_currency_kgs(self):
        captured = {}

        def fake_request(method, path, **kwargs):
            captured["payload"] = kwargs.get("json_payload")
            return True, {}

        with patch("payments.payplat_client._request", side_effect=fake_request):
            payplat_create_deal(
                amount=Decimal("1000"),
                shop_internal_id="oid",
                requisite_type="lkq",
                currency="kgs",
            )
        self.assertEqual(captured["payload"]["currency"], "kgs")
        self.assertEqual(captured["payload"]["requisite_type"], "lkq")
        self.assertNotIn("payer", captured["payload"])


class PayplatCardPhoneSplitTest(SimpleTestCase):
    def _melbet_payin(self, ps="C2CKZT"):
        merchant = type("M", (), {"user": type("U", (), {"username": "melbet"})()})()
        return type(
            "P",
            (),
            {
                "merchant": merchant,
                "payment_system": type("S", (), {"name": ps})(),
                "currency": type("C", (), {"symbol": "KZT"})(),
            },
        )()

    @override_settings(MELBET_KZT_USERNAMES="melbet,melbet_test")
    def test_melbet_c2ckzt_stays_h2h(self):
        self.assertEqual(payplat_requisite_type_for("C2CKZT", self._melbet_payin()), "h2h")

    def test_other_merchant_c2ckzt_stays_h2h(self):
        self.assertEqual(payplat_requisite_type_for("C2CKZT"), "h2h")

    def test_phonekzt_is_mobile(self):
        self.assertEqual(payplat_requisite_type_for("PHONEKZT"), "mobile")

    def test_c2ckgs_is_card_and_sends_kgs(self):
        self.assertEqual(payplat_requisite_type_for("C2CKGS"), "card")
        pay_in = type(
            "P",
            (),
            {
                "currency": type("C", (), {"symbol": "KGS"})(),
                "payment_system": type("S", (), {"name": "C2CKGS"})(),
            },
        )()
        self.assertEqual(payplat_deal_currency(pay_in), "kgs")
        self.assertIsNone(payplat_payer_for("C2CKGS", pay_in))

    def test_phonekgs_is_mobile(self):
        self.assertEqual(payplat_requisite_type_for("PHONEKGS"), "mobile")

    def test_card_type_rejects_phone_requisite(self):
        req = payplat_map_requisite({"requisite": {"phone_number": "+77001234567"}})
        self.assertFalse(payplat_requisite_matches_requested_type(req, "card"))
        self.assertTrue(payplat_requisite_matches_requested_type(req, "mobile"))
        card = payplat_map_requisite({"requisite": {"card_number": "4000000000000001"}})
        self.assertTrue(payplat_requisite_matches_requested_type(card, "card"))
        self.assertFalse(payplat_requisite_matches_requested_type(card, "mobile"))


class MelbetKgsMethodMapTest(TestCase):
    def test_resolves_kgs_methods(self):
        cfg = _Cfg(
            {
                "default_kgs": {"payment_system": "QRKGS", "currency": "KGS"},
                "qr_kgs": {"payment_system": "QRKGS", "currency": "KGS"},
                "default_kzt": {"payment_system": "C2CKZT", "currency": "KZT"},
            }
        )
        self.assertEqual(
            resolve_method_entry(cfg, currency="kgs", method="qr_kgs"),
            {"payment_system": "QRKGS", "currency": "KGS"},
        )
        self.assertEqual(
            resolve_method_entry(cfg, currency="KGS", method="unknown"),
            {"payment_system": "QRKGS", "currency": "KGS"},
        )
        self.assertEqual(
            resolve_method_entry(cfg, currency="kzt", method="card2card_kzt"),
            {"payment_system": "C2CKZT", "currency": "KZT"},
        )

    def test_resolves_card2card_kgs(self):
        cfg = _Cfg(
            {
                "qr_kgs": {"payment_system": "QRKGS", "currency": "KGS"},
                "card2card_kgs": {"payment_system": "C2CKGS", "currency": "KGS"},
                "phone_kgs": {"payment_system": "PHONEKGS", "currency": "KGS"},
            }
        )
        self.assertEqual(
            resolve_method_entry(cfg, currency="kgs", method="card2card_kgs"),
            {"payment_system": "C2CKGS", "currency": "KGS"},
        )
        self.assertEqual(
            resolve_method_entry(cfg, currency="kgs", method="phone_kgs"),
            {"payment_system": "PHONEKGS", "currency": "KGS"},
        )

    def test_resolves_phone_kzt(self):
        cfg = _Cfg(
            {
                "card2card_kzt": {"payment_system": "C2CKZT", "currency": "KZT"},
                "phone_kzt": {"payment_system": "PHONEKZT", "currency": "KZT"},
            }
        )
        self.assertEqual(
            resolve_method_entry(cfg, currency="kzt", method="phone_kzt"),
            {"payment_system": "PHONEKZT", "currency": "KZT"},
        )
