import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "titanpay.settings")
os.environ.setdefault("LOCAL", "true")
django.setup()

from django.test import SimpleTestCase

from trade.models import InOrder, OutOrder
from trade.order_id_query import apply_order_id_filter


class OrderIdFilterQueryTest(SimpleTestCase):
    def test_visible_suffix_compiles_for_payin_and_inorder(self):
        qs = apply_order_id_filter(InOrder.objects.all(), "444455556666", "pay_in")
        sql = str(qs.query).lower()
        self.assertIn("444455556666", sql)
        self.assertIn("payments_payin", sql)

    def test_full_uuid_matches_inorder_or_payin(self):
        qs = apply_order_id_filter(
            InOrder.objects.all(),
            "3f2a1c0e-1111-2222-3333-444455556666",
            "pay_in",
        )
        sql = str(qs.query).lower()
        self.assertIn("3f2a1c0e111122223333444455556666", sql)
        self.assertIn("payments_payin", sql)

    def test_payout_suffix_compiles(self):
        qs = apply_order_id_filter(OutOrder.objects.all(), "abcdef012345", "pay_out")
        sql = str(qs.query).lower()
        self.assertIn("abcdef012345", sql)
        self.assertIn("payments_payout", sql)

    def test_short_or_non_hex_returns_empty(self):
        short = apply_order_id_filter(InOrder.objects.all(), "abc", "pay_in")
        junk = apply_order_id_filter(InOrder.objects.all(), "заказ-123", "pay_in")
        self.assertTrue(short.query.is_empty())
        self.assertTrue(junk.query.is_empty())
