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
    check_merchant_conversion_alerts,
    check_psp_merchant_conversion_alerts,
    check_requisite_conversion_alerts,
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


def _fake_pay(merchant, psp, status, card="4111111111111111", client_id="c1", db_client_id=1):
    pay = MagicMock()
    pay.merchant_id = 1
    pay.merchant.user_id = 1
    pay.merchant.user.username = merchant
    pay.status_id = 1
    pay.status.name = status
    pay.client_id = db_client_id
    pay.client.client_id = client_id
    pay.order.payment_details_id = 1
    pay.order.payment_details.group.trader.user.username = psp
    pay.order.payment_details.card_number = card
    pay.order.payment_details.deposit_number = ""
    pay.order.payment_details.id = "pd-1"
    return pay


class MerchantConversionSpamAlertTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @override_settings(
        ADMIN_ALERT_CONV_WINDOW_MIN=15,
        ADMIN_ALERT_CONV_MIN_CREATED=10,
        ADMIN_ALERT_CONV_ISSUED_PCT_MIN=50,
        ADMIN_ALERT_CONV_MERCHANTS="mostbet",
        ADMIN_ALERT_CONV_SPAM_MERCHANTS="mostbet",
        ADMIN_ALERT_CONV_SPAM_MIN=3,
        ADMIN_ALERT_CONV_SPAM_TOP=3,
        ADMIN_ALERT_CONV_COOLDOWN_SEC=900,
        ADMIN_ALERT_BOT_TOKEN="t",
        ADMIN_ALERT_CHAT_ID="1",
    )
    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    @patch("payments.models.PayIn.objects.filter")
    def test_alert_includes_clean_conversion_without_spam(self, filt, send):
        # 6 spam Failed from one client + 4 Success from another → raw 40%, clean 100%
        rows = [
            _fake_pay("mostbet", "psp", "Failed", client_id="spam1", db_client_id=10)
            for _ in range(6)
        ]
        rows += [
            _fake_pay("mostbet", "psp", "Success", client_id="good1", db_client_id=11)
            for _ in range(4)
        ]
        qs = MagicMock()
        qs.select_related.return_value = qs
        qs.filter.return_value = qs
        qs.iterator.return_value = iter(rows)
        filt.return_value = qs

        check_merchant_conversion_alerts()
        self.assertEqual(send.call_count, 1)
        text = send.call_args.args[0]
        self.assertIn("iss→ok=40.00%", text)
        self.assertIn("iss→ok без спама=100.00%", text)
        self.assertIn("spam1×6", text)
        self.assertIn("clients=1", text)

    @override_settings(
        ADMIN_ALERT_CONV_WINDOW_MIN=15,
        ADMIN_ALERT_CONV_MIN_CREATED=10,
        ADMIN_ALERT_CONV_ISSUED_PCT_MIN=50,
        ADMIN_ALERT_CONV_MERCHANTS="pandapay",
        ADMIN_ALERT_CONV_SPAM_MERCHANTS="melbet,mostbet",
        ADMIN_ALERT_CONV_COOLDOWN_SEC=900,
        ADMIN_ALERT_BOT_TOKEN="t",
        ADMIN_ALERT_CHAT_ID="1",
    )
    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    @patch("payments.models.PayIn.objects.filter")
    def test_non_spam_merchant_has_no_spam_block(self, filt, send):
        rows = [_fake_pay("pandapay", "psp", "Failed", client_id="x") for _ in range(8)]
        rows += [_fake_pay("pandapay", "psp", "Success", client_id="y") for _ in range(2)]
        qs = MagicMock()
        qs.select_related.return_value = qs
        qs.filter.return_value = qs
        qs.iterator.return_value = iter(rows)
        filt.return_value = qs

        check_merchant_conversion_alerts()
        self.assertEqual(send.call_count, 1)
        text = send.call_args.args[0]
        self.assertNotIn("без спама", text)
        self.assertIn("iss→ok=20.00%", text)


class PspMerchantConversionAlertTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @override_settings(
        ADMIN_ALERT_PSP_CONV_WINDOW_MIN=60,
        ADMIN_ALERT_PSP_CONV_MIN_ISSUED=5,
        ADMIN_ALERT_PSP_CONV_ABS_PCT_MIN=10,
        ADMIN_ALERT_PSP_CONV_DROP_PP=12,
        ADMIN_ALERT_CONV_MERCHANTS="mostbet",
        ADMIN_ALERT_PSP_CONV_COOLDOWN_SEC=1200,
        ADMIN_ALERT_BOT_TOKEN="t",
        ADMIN_ALERT_CHAT_ID="1",
    )
    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    @patch("payments.models.PayIn.objects.filter")
    def test_alerts_when_psp_below_merchant_avg(self, filt, send):
        # merchant avg ~50% (10 ok / 20 iss); bad psp 10% (1/10)
        rows = [_fake_pay("mostbet", "gipay1", "Success") for _ in range(9)]
        rows += [_fake_pay("mostbet", "gipay1", "Failed") for _ in range(1)]
        rows += [_fake_pay("mostbet", "patriot1", "Success") for _ in range(1)]
        rows += [_fake_pay("mostbet", "patriot1", "Failed") for _ in range(9)]
        qs = MagicMock()
        qs.select_related.return_value = qs
        qs.filter.return_value = qs
        qs.iterator.return_value = iter(rows)
        filt.return_value = qs
        check_psp_merchant_conversion_alerts()
        self.assertEqual(send.call_count, 1)
        text = send.call_args.args[0]
        self.assertIn("patriot1", text)
        self.assertIn("mostbet", text)


class RequisiteConversionAlertTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @override_settings(
        ADMIN_ALERT_REQ_CONV_WINDOW_H=24,
        ADMIN_ALERT_REQ_CONV_MIN_ISSUED=5,
        ADMIN_ALERT_REQ_CONV_ABS_PCT_MIN=8,
        ADMIN_ALERT_CONV_MERCHANTS="mostbet",
        ADMIN_ALERT_REQ_CONV_COOLDOWN_SEC=3600,
        ADMIN_ALERT_BOT_TOKEN="t",
        ADMIN_ALERT_CHAT_ID="1",
    )
    @patch("payments.admin_alerts.send_admin_alert", return_value=True)
    @patch("payments.models.PayIn.objects.filter")
    def test_alerts_on_bad_requisite(self, filt, send):
        bad_card = "5555444433331111"
        rows = [_fake_pay("mostbet", "plutus1", "Failed", card=bad_card) for _ in range(6)]
        qs = MagicMock()
        qs.select_related.return_value = qs
        qs.filter.return_value = qs
        qs.iterator.return_value = iter(rows)
        filt.return_value = qs
        check_requisite_conversion_alerts()
        self.assertEqual(send.call_count, 1)
        text = send.call_args.args[0]
        self.assertIn("plutus1", text)
        self.assertIn("card:*1111", text)
