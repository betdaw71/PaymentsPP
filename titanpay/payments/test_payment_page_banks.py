from django.test import SimpleTestCase

from payments.bank_deeplinks import build_bank_actions
from payments.bank_guides import build_bank_guides
from payments.integrations.melbet.mapping import sender_bank_for_melbet_method


class MelbetPaymentPageBankTest(SimpleTestCase):
    def test_card2card_kzt_opens_kaspi_not_homebank(self):
        self.assertEqual(sender_bank_for_melbet_method("card2card_kzt"), "kaspi")
        self.assertEqual(sender_bank_for_melbet_method("card2card_kzt_kaspi"), "kaspi")

        actions = build_bank_actions(
            amount="10000",
            currency="KZT",
            payment_details={"card_number": "4714700048511624", "bank": "Другой", "owner": "TEST"},
            locale="kk",
            sender_bank=sender_bank_for_melbet_method("card2card_kzt"),
        )
        self.assertTrue(actions)
        self.assertEqual(actions[0]["id"], "kaspi")
        self.assertIn("Kaspi", actions[0]["label"])
        self.assertFalse(any(a["id"] == "halyk" for a in actions))

    def test_kzt_always_has_kaspi_guide_image(self):
        guides = build_bank_guides(currency="KZT", locale="kk", bank_actions=[{"id": "halyk", "label": "Homebank"}])
        self.assertEqual(len(guides), 1)
        self.assertIn("kaspi-international-transfers-guide.png", guides[0]["image_url"])
