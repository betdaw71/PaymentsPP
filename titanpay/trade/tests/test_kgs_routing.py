"""QRKGS / Melbet KGS PS must use SberRouting (same as C2C)."""
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from trade.routing.base import route, _c2c_style_ps_names
from trade.routing.ps_names import melbet_kgs_ps_names
from trade.routing.sber import SberRouting


class _PS:
    def __init__(self, name: str):
        self.name = name


class MelbetKgsRoutingTest(SimpleTestCase):
    def test_melbet_kgs_names_default(self):
        names = melbet_kgs_ps_names()
        self.assertIn("QRKGS", names)
        self.assertIn("C2CKGS", names)
        self.assertIn("PHONEKGS", names)

    def test_qrkgs_in_c2c_style(self):
        self.assertIn("QRKGS", _c2c_style_ps_names())

    def test_route_qrkgs_is_sber(self):
        router = route(_PS("QRKGS"))
        self.assertIsInstance(router, SberRouting)

    def test_route_unknown_still_fails(self):
        with self.assertRaises(ValidationError):
            route(_PS("NOT_A_REAL_PS_XYZ"))
