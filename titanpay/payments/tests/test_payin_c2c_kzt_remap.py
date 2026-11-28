"""Pandapay C2C KZT читается как C2CKZT. Остальные C2C KZT — локальный каскад."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings

from basics.models import Currency, PaymentSystem
from merchant.models import Merchant
from payments.payin_remap import remap_payin_payment_system_id
from payments.psp_payin import merchant_psp_priority_map, merchant_wants_psp_first, sort_groups_for_routing


def _merchant(username):
    return SimpleNamespace(user=SimpleNamespace(username=username))


def _ps(name, symbol):
    return SimpleNamespace(name=name, currency=SimpleNamespace(symbol=symbol))


def _group(username, pk, *, volume="0"):
    trader = SimpleNamespace(team_id=1, user=SimpleNamespace(username=username))
    return SimpleNamespace(
        pk=pk,
        id=pk,
        trader=trader,
        trader_id=pk,
        payment_system_id=1,
        current_volume=Decimal(volume),
    )


@override_settings(PAYIN_C2C_KZT_AS_C2CKZT_MERCHANTS="pandapay", C2C_NAME="C2C", C2CKZT_NAME="C2CKZT")
class PayinC2cKztRemapTest(TestCase):
    def setUp(self):
        self.kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        self.rub = Currency.objects.create(name="Ruble", symbol="RUB")
        self.c2c = PaymentSystem.objects.create(
            name="C2C", currency=self.kzt, required_fields={}, usdt_exchange_rate=Decimal("500")
        )
        self.c2c_rub = PaymentSystem.objects.create(
            name="C2C", currency=self.rub, required_fields={}, usdt_exchange_rate=Decimal("90")
        )
        self.c2ckzt = PaymentSystem.objects.create(
            name="C2CKZT", currency=self.kzt, required_fields={}, usdt_exchange_rate=Decimal("500")
        )
        panda = User.objects.create_user(username="pandapay", password="x")
        self.pandapay = Merchant.objects.create(user=panda)
        other = User.objects.create_user(username="aggrepay", password="x")
        self.aggrepay = Merchant.objects.create(user=other)

    def test_pandapay_c2c_kzt_becomes_c2ckzt(self):
        mapped = remap_payin_payment_system_id(
            {"payment_system": self.c2c.id, "currency": self.kzt.id}, self.pandapay
        )
        self.assertEqual(mapped["payment_system"], self.c2ckzt.id)

    def test_pandapay_c2c_rub_stays_c2c(self):
        mapped = remap_payin_payment_system_id(
            {"payment_system": self.c2c_rub.id}, self.pandapay
        )
        self.assertEqual(mapped["payment_system"], self.c2c_rub.id)

    def test_pandapay_c2ckzt_unchanged(self):
        mapped = remap_payin_payment_system_id(
            {"payment_system": self.c2ckzt.id}, self.pandapay
        )
        self.assertEqual(mapped["payment_system"], self.c2ckzt.id)

    def test_other_merchant_keeps_c2c_kzt(self):
        mapped = remap_payin_payment_system_id(
            {"payment_system": self.c2c.id}, self.aggrepay
        )
        self.assertEqual(mapped["payment_system"], self.c2c.id)


@override_settings(
    PAYIN_C2C_KZT_AS_C2CKZT_MERCHANTS="pandapay",
    PAYIN_LOCAL_C2C_KZT_MERCHANTS="pandapay_local_kzt,pandapay_kz_local",
    ASTRUM_TRADER_USERNAME="astrum_kzt",
    ASTRUM_LOCAL_TRADER_USERNAME="astrum_local_kzt",
    PROCHUB_TRADER_USERNAME="prochub1",
    AGGREPAY_ASTERISK_FIRST="1",
    PSP_ROUTING_PRIORITY_BY_MERCHANT={},
    PSP_ROUTING_SHARE_MAP={},
    HUMAN_ROUTING_FAIR="0",
)
@patch("payments.psp_payin._team_mdr_in_map", return_value={})
class LocalC2cKztCascadeTest(SimpleTestCase):
    def test_local_merchant_c2c_kzt_is_local_asterisk_then_prochub(self, _mdr):
        c2c = _ps("C2C", "KZT")
        merchant = _merchant("pandapay_kz_local")
        self.assertEqual(
            merchant_psp_priority_map(merchant, payment_system=c2c),
            {"astrum_local_kzt": 1, "prochub1": 2},
        )
        self.assertTrue(merchant_wants_psp_first(merchant, payment_system=c2c))
        groups = [
            _group("gipay1", 2),
            _group("astrum_kzt", 1),
            _group("prochub1", 4),
            _group("astrum_local_kzt", 3),
            _group("live_a", 21, volume="10"),
        ]
        ordered = sort_groups_for_routing(groups, merchant=merchant, payment_system=c2c)
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["astrum_local_kzt", "prochub1"],
        )

    def test_same_merchant_c2ckzt_keeps_transgran_asterisk(self, _mdr):
        c2ckzt = _ps("C2CKZT", "KZT")
        merchant = _merchant("aggrepay")
        self.assertEqual(
            merchant_psp_priority_map(merchant, payment_system=c2ckzt),
            {"astrum_kzt": 1},
        )
        groups = [
            _group("prochub1", 4),
            _group("astrum_local_kzt", 3),
            _group("astrum_kzt", 1),
            _group("live_a", 21, volume="10"),
        ]
        ordered = sort_groups_for_routing(groups, merchant=merchant, payment_system=c2ckzt)
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["astrum_kzt", "live_a"],
        )

    def test_aggrepay_c2c_kzt_keeps_current_asterisk_cascade(self, _mdr):
        c2c = _ps("C2C", "KZT")
        merchant = _merchant("aggrepay")
        self.assertEqual(
            merchant_psp_priority_map(merchant, payment_system=c2c),
            {"astrum_kzt": 1},
        )
        groups = [
            _group("gipay1", 2),
            _group("astrum_local_kzt", 3),
            _group("prochub1", 4),
            _group("astrum_kzt", 1),
            _group("live_a", 21, volume="10"),
        ]
        ordered = sort_groups_for_routing(groups, merchant=merchant, payment_system=c2c)
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["astrum_kzt", "live_a"],
        )

    def test_pandapay_c2c_kzt_is_not_the_local_cascade(self, _mdr):
        c2c = _ps("C2C", "KZT")
        merchant = _merchant("pandapay")
        mapping = merchant_psp_priority_map(merchant, payment_system=c2c) or {}
        self.assertNotIn("astrum_local_kzt", mapping)
        self.assertNotEqual(set(mapping), {"astrum_local_kzt", "prochub1"})
