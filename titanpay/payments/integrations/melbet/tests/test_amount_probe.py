from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from payments.integrations.melbet.amount_probe import melbet_candidate_amounts


class MelbetAmountProbeTest(SimpleTestCase):
    def _solution(self):
        return SimpleNamespace(
            merchant=SimpleNamespace(user=SimpleNamespace(username="melbet")),
            min_limit_in=Decimal("1000"),
            max_limit_in=Decimal("1000000"),
        )

    @override_settings(
        MELBET_AMOUNT_PROBE_ENABLED=True,
        MELBET_AMOUNT_PROBE_DELTAS="20,-20,50",
        MELBET_AMOUNT_PROBE_RANDOMIZE=False,
        MELBET_AMOUNT_PROBE_MAX_EXTRA=10,
    )
    @patch("payments.integrations.melbet.amount_probe.is_melbet_merchant", return_value=True)
    def test_candidate_amounts_keep_requested_first(self, _is_melbet):
        amounts = melbet_candidate_amounts(Decimal("10000"), self._solution())
        self.assertEqual(amounts[0], Decimal("10000.00"))
        self.assertIn(Decimal("10020.00"), amounts)
        self.assertIn(Decimal("9980.00"), amounts)
        self.assertIn(Decimal("10050.00"), amounts)

    @override_settings(MELBET_AMOUNT_PROBE_ENABLED=False)
    @patch("payments.integrations.melbet.amount_probe.is_melbet_merchant", return_value=True)
    def test_probe_disabled_returns_only_requested(self, _is_melbet):
        amounts = melbet_candidate_amounts(Decimal("10000"), self._solution())
        self.assertEqual(amounts, [Decimal("10000.00")])

    @override_settings(
        MELBET_AMOUNT_PROBE_ENABLED=True,
        MELBET_AMOUNT_PROBE_DELTAS="20,-20",
        MELBET_AMOUNT_PROBE_RANDOMIZE=False,
        MELBET_AMOUNT_PROBE_MAX_EXTRA=10,
    )
    @patch("payments.integrations.melbet.amount_probe.is_melbet_merchant", return_value=True)
    def test_candidate_amounts_respect_limits(self, _is_melbet):
        solution = self._solution()
        solution.min_limit_in = Decimal("10000")
        amounts = melbet_candidate_amounts(Decimal("10000"), solution)
        self.assertEqual(amounts, [Decimal("10000.00"), Decimal("10020.00")])
