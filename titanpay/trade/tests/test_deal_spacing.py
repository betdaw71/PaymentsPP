from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from trade.routing.deal_spacing import group_skip_reason_for_deal_spacing


class DealSpacingHelperTest(SimpleTestCase):
    def test_disabled_when_zero(self):
        group = SimpleNamespace(id="g1", amount_diff=0, deal_interval_sec=0)
        self.assertIsNone(group_skip_reason_for_deal_spacing(group, Decimal("5000")))

    @patch("trade.models.InOrder.objects.filter")
    def test_amount_diff_blocks_close_active(self, filt):
        group = SimpleNamespace(id="g1", amount_diff=Decimal("500"), deal_interval_sec=0)
        active_qs = MagicMock()
        active_qs.values_list.return_value = [Decimal("5000")]
        filt.return_value = active_qs

        self.assertEqual(
            group_skip_reason_for_deal_spacing(group, Decimal("5200")),
            "amount_diff",
        )

        active_qs.values_list.return_value = [Decimal("5000")]
        self.assertIsNone(group_skip_reason_for_deal_spacing(group, Decimal("5500")))

    @patch("trade.models.InOrder.objects.filter")
    def test_interval_blocks_recent_issue(self, filt):
        group = SimpleNamespace(id="g1", amount_diff=0, deal_interval_sec=300)
        recent = timezone.now() - timedelta(seconds=60)
        qs = MagicMock()
        qs.exclude.return_value = qs
        qs.order_by.return_value = qs
        qs.values_list.return_value = MagicMock(first=MagicMock(return_value=recent))
        filt.return_value = qs
        self.assertEqual(group_skip_reason_for_deal_spacing(group, Decimal("5000")), "deal_interval")
