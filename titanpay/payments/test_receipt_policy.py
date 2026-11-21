from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from payments.receipt_policy import receipt_required_for_payin


def _payin(*, username="shop", currency="KZT", ps="C2CKZT", has_melbet_session=False):
    pay_in = SimpleNamespace(
        merchant=SimpleNamespace(user=SimpleNamespace(username=username)),
        currency=SimpleNamespace(symbol=currency),
        payment_system=SimpleNamespace(name=ps),
    )
    if has_melbet_session:
        pay_in.melbet_session = SimpleNamespace(melbet_method="card")
    return pay_in


class ReceiptPolicyTest(SimpleTestCase):
    @override_settings(MELBET_KZT_USERNAMES="melbet,melbet_test")
    def test_melbet_kzt_does_not_require_receipt(self):
        self.assertFalse(receipt_required_for_payin(_payin(username="melbet")))
        self.assertFalse(receipt_required_for_payin(_payin(username="melbet_test")))

    @override_settings(MELBET_KZT_USERNAMES="melbet,melbet_test")
    def test_other_kzt_merchant_still_requires_receipt(self):
        self.assertTrue(receipt_required_for_payin(_payin(username="pandapay")))

    @override_settings(MELBET_KZT_USERNAMES="melbet,melbet_test")
    def test_melbet_session_skips_receipt_even_if_username_differs(self):
        self.assertFalse(
            receipt_required_for_payin(_payin(username="other", has_melbet_session=True))
        )

    def test_non_kzt_without_listed_ps_does_not_require_receipt(self):
        self.assertFalse(receipt_required_for_payin(_payin(currency="RUB", ps="Sber")))
