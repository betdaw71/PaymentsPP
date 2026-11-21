"""Melbet payout CB must not fall back to AvaPay format when session is missing."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from payments.integrations.melbet.callbacks import (
    ensure_melbet_payout_session,
    try_send_melbet_payout_callback,
)


class MelbetPayoutCallbackTest(SimpleTestCase):
    @patch("payments.integrations.melbet.callbacks._schedule_melbet_callback")
    @patch("payments.integrations.melbet.callbacks.ensure_melbet_payout_session")
    def test_success_schedules_melbet_cb(self, ensure_mock, schedule_mock):
        session = MagicMock()
        session.order_id = "w5547812021"
        ensure_mock.return_value = session
        pay_out = SimpleNamespace(
            id="po-1",
            callback_url="https://melbet.example/cb",
            merchant_order_id="w5547812021",
        )
        handled = try_send_melbet_payout_callback(pay_out, status_name="Success")
        self.assertTrue(handled)
        schedule_mock.assert_called_once_with(session, pay_out.callback_url)

    @patch("payments.integrations.melbet.callbacks._schedule_melbet_callback")
    @patch("payments.integrations.melbet.callbacks.ensure_melbet_payout_session")
    def test_missing_session_falls_through(self, ensure_mock, schedule_mock):
        ensure_mock.return_value = None
        pay_out = SimpleNamespace(callback_url="https://x", merchant_order_id="x")
        handled = try_send_melbet_payout_callback(pay_out, status_name="Success")
        self.assertFalse(handled)
        schedule_mock.assert_not_called()

    @patch("payments.integrations.melbet.callbacks.MelbetTransactionSession")
    @patch("payments.integrations.melbet.callbacks._melbet_config_for_merchant")
    @patch("payments.integrations.melbet.callbacks._melbet_session_for_payout")
    def test_ensure_recreates_session(self, for_payout_mock, config_mock, session_model):
        for_payout_mock.return_value = None
        session_model.objects.filter.return_value.select_related.return_value.first.return_value = None
        config = MagicMock()
        config_mock.return_value = config
        created = MagicMock()
        session_model.objects.create.return_value = created

        pay_out = SimpleNamespace(
            id="po-1",
            merchant=MagicMock(),
            merchant_order_id="w5547812021",
            details={"phone": "+996111111111"},
            payment_system=SimpleNamespace(name="PHONEKGS"),
        )
        got = ensure_melbet_payout_session(pay_out)
        self.assertIs(got, created)
        session_model.objects.create.assert_called_once()
        kwargs = session_model.objects.create.call_args.kwargs
        self.assertEqual(kwargs["order_id"], "w5547812021")
        self.assertEqual(kwargs["pay_out"], pay_out)
        self.assertEqual(kwargs["config"], config)
