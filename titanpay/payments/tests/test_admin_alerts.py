from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from basics.models import Balance
from merchant.models import Merchant
from payments.admin_alerts import (
    check_appeal_closure_alerts,
    check_merchant_balance_alerts,
    note_payplat_issuance_failure,
    notify_threshold_once,
    notify_with_cooldown,
)


class ThresholdLatchTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    def test_sends_once_while_active(self, send):
        self.assertTrue(notify_threshold_once("k", True, "hi"))
        self.assertFalse(notify_threshold_once("k", True, "hi"))
        self.assertEqual(send.call_count, 1)
        notify_threshold_once("k", False, "hi")
        self.assertTrue(notify_threshold_once("k", True, "hi"))
        self.assertEqual(send.call_count, 2)

    @patch("payments.admin_alerts.send_admin_alert", return_value=False)
    def test_failed_send_does_not_latch(self, _send):
        self.assertFalse(notify_threshold_once("k", True, "hi"))
        cache_key = "admin_alert:k"
        self.assertFalse(cache.get(cache_key))


@override_settings(ADMIN_ALERT_BOT_TOKEN="t", ADMIN_ALERT_CHAT_ID="1")
class BalanceAlertTest(TestCase):
    def setUp(self):
        cache.clear()
        panda_user = User.objects.create_user(username="pandapay", password="x")
        panda_bal = Balance.objects.create(type=0, amount=Decimal("2801"))
        Merchant.objects.create(user=panda_user, balance=panda_bal)

        aggre_user = User.objects.create_user(username="aggrepay", password="x")
        aggre_bal = Balance.objects.create(type=0, amount=Decimal("3999"))
        Merchant.objects.create(user=aggre_user, balance=aggre_bal)

        melbet_user = User.objects.create_user(username="melbet", password="x")
        melbet_usdt = Balance.objects.create(type=0, amount=Decimal("0"))
        melbet_kzt = Balance.objects.create(type=0, amount=Decimal("-1499999"))
        Merchant.objects.create(user=melbet_user, balance=melbet_usdt, balance_kzt=melbet_kzt)

        mostbet_user = User.objects.create_user(username="mostbet", password="x")
        mostbet_bal = Balance.objects.create(type=0, amount=Decimal("1000"))
        Merchant.objects.create(user=mostbet_user, balance=mostbet_bal)

    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    def test_panda_high_and_melbet_above_negative_threshold(self, send):
        check_merchant_balance_alerts()
        texts = [call.args[0] for call in send.call_args_list]
        self.assertTrue(any("Panda Pay" in t for t in texts))
        self.assertTrue(any("Melbet" in t for t in texts))
        self.assertFalse(any("Aggrepay" in t for t in texts))
        self.assertFalse(any("Mostbet" in t for t in texts))
        check_merchant_balance_alerts()
        self.assertEqual(send.call_count, 2)


class CooldownAndPayplatBurstTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    def test_cooldown_blocks_repeat(self, send):
        self.assertTrue(notify_with_cooldown("x", "hi", 600))
        self.assertFalse(notify_with_cooldown("x", "hi", 600))
        self.assertEqual(send.call_count, 1)

    @override_settings(
        ADMIN_ALERT_PAYPLAT_FAIL_BURST=3,
        ADMIN_ALERT_PAYPLAT_FAIL_WINDOW_SEC=300,
        ADMIN_ALERT_PAYPLAT_COOLDOWN_SEC=600,
        ADMIN_ALERT_BOT_TOKEN="t",
        ADMIN_ALERT_CHAT_ID="1",
    )
    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    def test_payplat_burst_alerts_on_third_fail(self, send):
        pay_in = MagicMock()
        pay_in.id = "abc"
        pay_in.amount = Decimal("5000")
        pay_in.merchant.user.username = "mostbet"
        pay_in.payment_system.name = "C2CKZT"
        note_payplat_issuance_failure(pay_in, reason="no_requisite")
        note_payplat_issuance_failure(pay_in, reason="no_requisite")
        self.assertEqual(send.call_count, 0)
        note_payplat_issuance_failure(pay_in, reason="no_requisite")
        self.assertEqual(send.call_count, 1)
        self.assertIn("PayPlat", send.call_args.args[0])


class AppealClosureAlertTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @override_settings(
        ADMIN_ALERT_APPEAL_WINDOW_MIN=60,
        ADMIN_ALERT_APPEAL_MIN_SUCCESS=8,
        ADMIN_ALERT_APPEAL_MIN_APPROVED=2,
        ADMIN_ALERT_APPEAL_PCT_MAX=20,
        ADMIN_ALERT_APPEAL_GROWTH_PP=10,
        ADMIN_ALERT_APPEAL_MERCHANTS="mostbet",
        ADMIN_ALERT_APPEAL_COOLDOWN_SEC=1800,
        ADMIN_ALERT_BOT_TOKEN="t",
        ADMIN_ALERT_CHAT_ID="1",
    )
    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    @patch("payments.admin_alerts._appeal_closure_stats")
    def test_alerts_on_high_appeal_pct(self, stats, send):
        # each check() calls stats twice: current, previous
        high = {"mostbet": {"success": 10, "appeal_ok": 4}}  # 40%
        low = {"mostbet": {"success": 10, "appeal_ok": 1}}  # 10%
        stats.side_effect = [high, low, high, low]
        check_appeal_closure_alerts()
        self.assertEqual(send.call_count, 1)
        text = send.call_args.args[0]
        self.assertIn("апелляционного закрытия mostbet", text)
        self.assertIn("40%", text)
        check_appeal_closure_alerts()
        self.assertEqual(send.call_count, 1)  # cooldown

    @override_settings(
        ADMIN_ALERT_APPEAL_WINDOW_MIN=60,
        ADMIN_ALERT_APPEAL_MIN_SUCCESS=8,
        ADMIN_ALERT_APPEAL_MIN_APPROVED=2,
        ADMIN_ALERT_APPEAL_PCT_MAX=50,
        ADMIN_ALERT_APPEAL_GROWTH_PP=10,
        ADMIN_ALERT_APPEAL_MERCHANTS="mostbet",
        ADMIN_ALERT_APPEAL_COOLDOWN_SEC=1800,
        ADMIN_ALERT_BOT_TOKEN="t",
        ADMIN_ALERT_CHAT_ID="1",
    )
    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    @patch("payments.admin_alerts._appeal_closure_stats")
    def test_alerts_on_growth_even_below_max(self, stats, send):
        stats.side_effect = [
            {"mostbet": {"success": 10, "appeal_ok": 3}},  # 30% < 50 max
            {"mostbet": {"success": 10, "appeal_ok": 1}},  # 10% → +20pp
        ]
        check_appeal_closure_alerts()
        self.assertEqual(send.call_count, 1)
        self.assertIn("рост", send.call_args.args[0].lower())

    @override_settings(
        ADMIN_ALERT_APPEAL_WINDOW_MIN=60,
        ADMIN_ALERT_APPEAL_MIN_SUCCESS=8,
        ADMIN_ALERT_APPEAL_MIN_APPROVED=2,
        ADMIN_ALERT_APPEAL_PCT_MAX=20,
        ADMIN_ALERT_APPEAL_GROWTH_PP=10,
        ADMIN_ALERT_APPEAL_MERCHANTS="mostbet",
        ADMIN_ALERT_BOT_TOKEN="t",
        ADMIN_ALERT_CHAT_ID="1",
    )
    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    @patch("payments.admin_alerts._appeal_closure_stats")
    def test_no_alert_when_below_thresholds(self, stats, send):
        stats.side_effect = [
            {"mostbet": {"success": 10, "appeal_ok": 1}},  # 10%
            {"mostbet": {"success": 10, "appeal_ok": 1}},
        ]
        check_appeal_closure_alerts()
        self.assertEqual(send.call_count, 0)
