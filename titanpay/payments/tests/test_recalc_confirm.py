from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from contextlib import nullcontext

from django.test import SimpleTestCase

from payments.recalc_confirm import apply_recalc_decision, format_recalc_prompt, parse_recalc_callback


class RecalcCallbackParseTest(SimpleTestCase):
    def test_confirm_and_reject(self):
        order_id = "3f2a1c0e-1111-2222-3333-444455556666"
        self.assertEqual(parse_recalc_callback(f"rin:y:{order_id}"), ("rin", order_id, True))
        self.assertEqual(parse_recalc_callback(f"rout:n:{order_id}"), ("rout", order_id, False))
        self.assertIsNone(parse_recalc_callback("rin:y:not-a-uuid"))
        self.assertIsNone(parse_recalc_callback("/lookup 1"))

    def test_prompt_shows_both_amounts(self):
        text = format_recalc_prompt(
            side="rin",
            order_id="order-1",
            merchant="melbet",
            trader="resdfe",
            currency="KZT",
            amount=Decimal("3000"),
            new_amount=Decimal("2500"),
            merchant_order_id="24781441961",
            pay_id="pay-1",
        )
        self.assertIn("Перерасчёт входящей заявки", text)
        self.assertIn("Было: 3000.00 KZT", text)
        self.assertIn("Стало: 2500.00 KZT", text)
        self.assertIn("melbet", text)
        self.assertIn("resdfe", text)
        self.assertIn("24781441961", text)


class RecalcDecisionTest(SimpleTestCase):
    def test_confirm_applies_proposed_amount(self):
        order = SimpleNamespace(
            status_id=1,
            status=SimpleNamespace(name="Recalculation"),
            recalculated_amount=Decimal("2500"),
            support_recalculate=lambda amount: setattr(order, "applied", amount),
            cancel_by_support=lambda: setattr(order, "cancelled", True),
        )
        with patch("payments.recalc_confirm.transaction.atomic", nullcontext), patch(
            "payments.recalc_confirm._locked", return_value=order
        ):
            result = apply_recalc_decision("rin", str(uuid4()), True)
        self.assertIn("Подтверждено", result)
        self.assertEqual(order.applied, Decimal("2500"))

    def test_reject_cancels_payin(self):
        order = SimpleNamespace(
            status_id=1,
            status=SimpleNamespace(name="Recalculation"),
            recalculated_amount=Decimal("2500"),
            cancel_by_support=lambda: setattr(order, "cancelled", True),
        )
        with patch("payments.recalc_confirm.transaction.atomic", nullcontext), patch(
            "payments.recalc_confirm._locked", return_value=order
        ):
            result = apply_recalc_decision("rin", str(uuid4()), False)
        self.assertTrue(order.cancelled)
        self.assertIn("Отклонено", result)

    def test_second_click_does_not_apply_again(self):
        order = SimpleNamespace(
            status_id=1,
            status=SimpleNamespace(name="Completed"),
            recalculated_amount=Decimal("2500"),
            support_recalculate=lambda amount: (_ for _ in ()).throw(AssertionError("applied twice")),
        )
        with patch("payments.recalc_confirm.transaction.atomic", nullcontext), patch(
            "payments.recalc_confirm._locked", return_value=order
        ):
            result = apply_recalc_decision("rin", str(uuid4()), True)
        self.assertIn("Уже обработано", result)
        self.assertIn("Completed", result)
