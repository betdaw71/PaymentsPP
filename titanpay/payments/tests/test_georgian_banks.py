from django.test import SimpleTestCase, override_settings

from payments.georgian_banks import (
    bank_name_is_georgian,
    detail_bank_is_georgian,
    merchant_blocks_georgian_banks,
    payplat_external_id,
)


class _User:
    def __init__(self, username):
        self.username = username


class _Merchant:
    def __init__(self, username):
        self.user = _User(username)


class _Ps:
    def __init__(self, name):
        self.name = name


class _Group:
    def __init__(self, name):
        self.payment_system = _Ps(name)


class _Detail:
    def __init__(self, bank_name="", ps_name="C2CKZT"):
        self.bank_name = bank_name
        self.group = _Group(ps_name)


class _Session:
    def __init__(self, body):
        self.create_response = body


class _PayIn:
    def __init__(self, merchant_name, payin_id="11111111-1111-1111-1111-111111111111"):
        self.id = payin_id
        self.merchant = None
        self.order = type("O", (), {"solution": type("S", (), {"merchant": _Merchant(merchant_name)})()})()


class GeorgianBankNameTest(SimpleTestCase):
    def test_blocks_tbc_georgia_and_bog(self):
        for name in (
            "TBC",
            "tbc",
            "TBC Bank",
            "tbcbank_ge",
            "TBС",
            "Bank of Georgia",
            "bank of gorgia",
            "BOG",
            "BOG Bank",
        ):
            self.assertTrue(bank_name_is_georgian(name), name)

    def test_allows_other_banks(self):
        for name in ("", "Kaspi", "Halyk", "Optima", "O bank", "MBank", "Elkard", "C2CKZT"):
            self.assertFalse(bank_name_is_georgian(name), name)

    @override_settings(GEORGIAN_BANK_BLOCK_MERCHANTS="artur_kids")
    def test_only_artur_kids(self):
        self.assertTrue(merchant_blocks_georgian_banks(_Merchant("artur_kids")))
        self.assertTrue(merchant_blocks_georgian_banks(_Merchant("Artur_kids")))
        self.assertFalse(merchant_blocks_georgian_banks(_Merchant("melbet")))
        self.assertFalse(merchant_blocks_georgian_banks(_Merchant("aggrepay")))
        self.assertFalse(merchant_blocks_georgian_banks(None))

    def test_human_card_uses_bank_field_not_method_name(self):
        self.assertFalse(detail_bank_is_georgian(_Detail(ps_name="C2CKZT")))
        self.assertTrue(detail_bank_is_georgian(_Detail(bank_name="TBC Bank")))
        self.assertFalse(detail_bank_is_georgian(_Detail(bank_name="Kaspi")))

    @override_settings(GEORGIAN_BANK_BLOCK_MERCHANTS="artur_kids")
    def test_payplat_retry_uses_new_deal_id_only_for_artur(self):
        artur = _PayIn("artur_kids")
        other = _PayIn("melbet")
        blocked = _Session({"error": "georgian_bank_blocked", "attempt": 1, "bank": "TBC"})
        self.assertEqual(payplat_external_id(artur, _Session({})), str(artur.id))
        self.assertEqual(payplat_external_id(artur, blocked), f"{artur.id}:2")
        self.assertEqual(payplat_external_id(other, blocked), str(other.id))
