import unittest

from payments.integrations.melbet.mapping import account_number_to_details


class AccountNumberToDetailsTest(unittest.TestCase):
    def test_c2ckgs_includes_bank(self):
        d = account_number_to_details("4400 1234 5678 9012", "C2CKGS")
        self.assertEqual(d.get("card_number"), "4400123456789012")
        self.assertEqual(d.get("bank_name"), "MBank")

    def test_phonekgs_includes_bank(self):
        d = account_number_to_details("+996700123456", "PHONEKGS")
        self.assertEqual(d.get("phone"), "+996700123456")
        self.assertEqual(d.get("bank_name"), "MBank")

    def test_qrkgs_fills_required(self):
        d = account_number_to_details("+996700123456", "QRKGS")
        self.assertEqual(d.get("phone"), "+996700123456")
        self.assertTrue(d.get("qr_payload"))
        self.assertEqual(d.get("bank_name"), "MBank")
