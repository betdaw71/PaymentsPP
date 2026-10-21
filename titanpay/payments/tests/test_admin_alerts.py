from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from basics.models import Balance
from merchant.models import Merchant
from payments.admin_alerts import check_merchant_balance_alerts, notify_threshold_once


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
        melbet_kzt = Balance.objects.create(type=0, amount=Decimal("100"))
        Merchant.objects.create(user=melbet_user, balance=melbet_usdt, balance_kzt=melbet_kzt)

        mostbet_user = User.objects.create_user(username="mostbet", password="x")
        mostbet_bal = Balance.objects.create(type=0, amount=Decimal("1000"))
        Merchant.objects.create(user=mostbet_user, balance=mostbet_bal)

    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    def test_panda_high_and_melbet_low(self, send):
        check_merchant_balance_alerts()
        texts = [call.args[0] for call in send.call_args_list]
        self.assertTrue(any("Panda Pay" in t for t in texts))
        self.assertTrue(any("Melbet" in t for t in texts))
        self.assertFalse(any("Aggrepay" in t for t in texts))
        self.assertFalse(any("Mostbet" in t for t in texts))
        check_merchant_balance_alerts()
        self.assertEqual(send.call_count, 2)
