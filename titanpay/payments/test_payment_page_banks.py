from django.test import SimpleTestCase

from payments.bank_deeplinks import (
    build_bank_actions,
    get_halyk_android_intent,
    get_halyk_primary_deeplink,
    get_kaspi_android_intent,
    get_kaspi_primary_deeplink,
)
from payments.bank_guides import build_bank_guides
from payments.integrations.melbet.mapping import sender_bank_for_melbet_method


class MelbetPaymentPageBankTest(SimpleTestCase):
    def test_card2card_kzt_kaspi_opens_kaspi_not_homebank(self):
        self.assertEqual(sender_bank_for_melbet_method("card2card_kzt_kaspi"), "kaspi")

        actions = build_bank_actions(
            amount="10000",
            currency="KZT",
            payment_details={"card_number": "4714700048511624", "bank": "Другой", "owner": "TEST"},
            locale="kk",
            sender_bank=sender_bank_for_melbet_method("card2card_kzt_kaspi"),
        )
        self.assertTrue(actions)
        self.assertEqual(actions[0]["id"], "kaspi")
        self.assertIn("Kaspi", actions[0]["label"])
        self.assertFalse(any(a["id"] == "halyk" for a in actions))

    def test_card2card_kzt_and_halyk_open_homebank_foreign_transfer(self):
        self.assertEqual(sender_bank_for_melbet_method("card2card_kzt"), "halyk")
        self.assertEqual(sender_bank_for_melbet_method("card2card_kzt_halyk"), "halyk")
        self.assertEqual(sender_bank_for_melbet_method("card2card_kzt_homebank"), "halyk")
        self.assertEqual(sender_bank_for_melbet_method("c2ckzt"), "halyk")

        actions = build_bank_actions(
            amount="10000",
            currency="KZT",
            payment_details={"card_number": "4714700048511624", "bank": "Другой", "owner": "TEST"},
            locale="ru",
            sender_bank=sender_bank_for_melbet_method("card2card_kzt_halyk"),
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["id"], "halyk")
        self.assertIn("Homebank", actions[0]["label"])
        self.assertTrue(actions[0]["url"].startswith("https://homebank.kz/transfers/foreign_card"))
        self.assertIn("4714700048511624", actions[0]["url"])
        self.assertIn("10000", actions[0]["url"])
        self.assertNotIn("intent://", actions[0]["url"])
        self.assertTrue(actions[0]["android_url"].startswith("intent://"))
        self.assertIn("kz.kkb.homebank", actions[0]["android_url"])
        self.assertIn("зарубежную карту", actions[0]["hint"])
        self.assertFalse(any(a["id"].startswith("kaspi") for a in actions))

    def test_halyk_primary_is_https_foreign_card_universal_link(self):
        url = get_halyk_primary_deeplink(card="4714700048511624", amount="10800")
        self.assertEqual(
            url,
            "https://homebank.kz/transfers/foreign_card?card=4714700048511624&amount=10800",
        )
        android = get_halyk_android_intent(card="4714700048511624", amount="10800")
        self.assertTrue(android.startswith("intent://homebank.kz/transfers/foreign_card"))
        self.assertIn("package=kz.kkb.homebank", android)

    def test_kaspi_primary_is_https_transfers_universal_link(self):
        url = get_kaspi_primary_deeplink(
            card="4714700048511624",
            amount="10000",
            owner="TEST",
            external_bank=True,
        )
        self.assertTrue(url.startswith("https://kaspi.kz/"))
        self.assertIn("/transfers/", url)
        self.assertIn("card_to_card", url)
        self.assertNotIn("intent://", url)
        self.assertIn("4714700048511624", url)
        self.assertIn("10000", url)

        android = get_kaspi_android_intent(
            card="4714700048511624",
            amount="10000",
            external_bank=True,
        )
        self.assertTrue(android.startswith("intent://"))
        self.assertIn("kz.kaspi.mobile", android)

        actions = build_bank_actions(
            amount="10800",
            currency="KZT",
            payment_details={"card_number": "4714700048511624", "bank": "Другой", "owner": "TEST"},
            locale="ru",
            sender_bank="kaspi",
        )
        self.assertEqual(actions[0]["id"], "kaspi")
        self.assertTrue(actions[0]["url"].startswith("https://kaspi.kz/"))
        self.assertIn("/transfers/", actions[0]["url"])
        self.assertNotIn("intent://", actions[0]["url"])
        self.assertTrue(actions[0]["android_url"].startswith("intent://"))
        self.assertIn("Переводы", actions[0]["hint"])

    def test_kaspi_to_kaspi_uses_client_transfers_path(self):
        url = get_kaspi_primary_deeplink(
            card="4405639732161086",
            amount="5000",
            external_bank=False,
        )
        self.assertTrue(url.startswith("https://kaspi.kz/"))
        self.assertIn("/transfers/client", url)
        self.assertNotIn("intent://", url)

    def test_kzt_kaspi_guide_image_only_for_kaspi_actions(self):
        kaspi_guides = build_bank_guides(
            currency="KZT", locale="kk", bank_actions=[{"id": "kaspi", "label": "Kaspi"}]
        )
        self.assertEqual(len(kaspi_guides), 1)
        self.assertIn("kaspi-international-transfers-guide.png", kaspi_guides[0]["image_url"])

        halyk_guides = build_bank_guides(
            currency="KZT", locale="ru", bank_actions=[{"id": "halyk", "label": "Homebank"}]
        )
        self.assertEqual(len(halyk_guides), 1)
        self.assertEqual(halyk_guides[0]["id"], "halyk_foreign")
        self.assertEqual(halyk_guides[0]["image_url"], "")
        self.assertIn("зарубежную карту", halyk_guides[0]["caption"])
        self.assertNotIn("kaspi", halyk_guides[0]["image_url"].lower())
