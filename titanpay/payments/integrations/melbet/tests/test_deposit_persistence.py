"""Melbet deposit: failed allocation must leave PayIn/InOrder in DB (no outer rollback)."""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from payments.integrations.melbet.services import MelbetServiceError, _fail_melbet_deposit_allocation


class MelbetDepositPersistenceTest(SimpleTestCase):
    @patch("payments.integrations.melbet.services.decline_payin")
    def test_allocation_failure_raises_after_decline(self, decline_mock):
        pay_in = MagicMock()
        with self.assertRaises(MelbetServiceError) as ctx:
            _fail_melbet_deposit_allocation(pay_in, send_callback=False)
        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("requisites", str(ctx.exception))
        decline_mock.assert_called_once_with(pay_in, send_callback=False)
