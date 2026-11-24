from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from trade.models import InOrder


class HumanCompletedRecalcLedgerTest(SimpleTestCase):
    def _order(self):
        return SimpleNamespace(
            solution=SimpleNamespace(
                merchant=SimpleNamespace(balance="merchant-balance"),
                payment_system="ps",
            )
        )

    def _run(self, *, psp: bool, new_charge: str):
        calls = []
        trader = SimpleNamespace(balance_usdt="working", frozen_balance_usdt="frozen")

        def create(**kwargs):
            calls.append(kwargs)

        with patch("payments.psp_payin.is_psp_trader", return_value=psp), patch(
            "merchant.kzt_settlement.uses_melbet_fiat_settlement", return_value=False
        ), patch("basics.models.Balance.objects") as balances, patch(
            "trade.models.TransactionType.objects"
        ) as types, patch("trade.models.Transaction.create", side_effect=create), patch(
            "appeals.services._cover_freeze_from_insurance"
        ) as cover, patch("payments.psp_payin.ensure_psp_frozen_for_complete") as ensure:
            balances.get.side_effect = lambda **kwargs: kwargs
            types.get.side_effect = lambda name: name
            InOrder._apply_completed_recalc_ledger(
                self._order(),
                trader,
                old_charge_usd=Decimal("6.00"),
                old_for_merchant=Decimal("5.50"),
                old_for_trader=Decimal("0.30"),
                new_charge_usd=Decimal(new_charge),
                new_for_merchant=Decimal("9.20"),
                new_for_trader=Decimal("0.50"),
            )
        return calls, cover, ensure

    def test_human_increase_covers_shortfall_and_charges_working_balance(self):
        calls, cover, ensure = self._run(psp=False, new_charge="10.00")
        cover.assert_called_once()
        self.assertEqual(cover.call_args.args[1], Decimal("4.00"))
        ensure.assert_not_called()
        principal = calls[0]
        self.assertEqual(principal["_from"], "working")
        self.assertEqual(principal["value"], Decimal("4.00"))
        self.assertEqual(principal["_comment"], "Success recalculation")
        self.assertEqual(principal["_transaction_type"], "Charge")

    def test_psp_increase_still_uses_frozen_balance(self):
        calls, cover, ensure = self._run(psp=True, new_charge="10.00")
        cover.assert_not_called()
        ensure.assert_called_once()
        self.assertEqual(calls[0]["_from"], "frozen")
        self.assertEqual(calls[0]["_comment"], "PSP completed recalculation")
