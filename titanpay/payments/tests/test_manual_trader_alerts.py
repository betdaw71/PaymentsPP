from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from payments.admin_alerts import (
    check_manual_trader_balance_alerts,
    check_manual_trader_conversion_alerts,
)


@override_settings(
    ADMIN_ALERT_BOT_TOKEN="t",
    ADMIN_ALERT_CHAT_ID="1",
    ADMIN_ALERT_MANUAL_BAL_MIN="50",
    ADMIN_ALERT_MANUAL_BAL_PCT="10",
    ADMIN_ALERT_MANUAL_DEFAULT_DEPOSIT="500",
)
class ManualTraderBalanceAlertTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    @patch("payments.admin_alerts._manual_traders_qs")
    def test_alerts_when_balance_near_deposit_floor(self, traders_qs, send):
        bal = SimpleNamespace(amount=Decimal("40"))
        trader = SimpleNamespace(
            user_id=1,
            user=SimpleNamespace(username="live1"),
            balance_usdt_id=1,
            balance_usdt=bal,
            working_deposit=Decimal("500"),
            team=None,
        )
        traders_qs.return_value = [trader]
        check_manual_trader_balance_alerts()
        self.assertEqual(send.call_count, 1)
        self.assertIn("live1", send.call_args.args[0])
        check_manual_trader_balance_alerts()
        self.assertEqual(send.call_count, 1)


@override_settings(
    ADMIN_ALERT_BOT_TOKEN="t",
    ADMIN_ALERT_CHAT_ID="1",
    ADMIN_ALERT_MANUAL_CONV_WINDOW_MIN=60,
    ADMIN_ALERT_MANUAL_CONV_MIN_ISSUED=5,
    ADMIN_ALERT_MANUAL_CONV_DROP_PP=10,
    ADMIN_ALERT_MANUAL_CONV_ABS_PCT_MIN=50,
    ADMIN_ALERT_MANUAL_CONV_EWMA_ALPHA="1",
    ADMIN_ALERT_MANUAL_CONV_COOLDOWN_SEC=60,
)
class ManualTraderConversionAlertTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    @patch("payments.admin_alerts._manual_trader_conv_stats")
    def test_alerts_on_low_conversion_with_volume(self, stats, send):
        stats.return_value = {
            "live1": {"created": 10, "declined": 0, "success": 1},
        }
        check_manual_trader_conversion_alerts()
        self.assertEqual(send.call_count, 1)
        self.assertIn("iss→ok=10.00%", send.call_args.args[0])
