from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from payments.admin_bot import _handle_site_withdraw, parse_command


class AdminBotParseTest(SimpleTestCase):
    def test_set_provider(self):
        cmd = parse_command("обнови баланс провайдера payplat1 на 1234.56")
        self.assertEqual(cmd["op"], "set")
        self.assertEqual(cmd["kind"], "trader")
        self.assertEqual(cmd["username"], "payplat1")
        self.assertEqual(cmd["amount"], Decimal("1234.56"))

    def test_cash(self):
        cmd = parse_command("касса")
        self.assertEqual(cmd["op"], "cash")

    def test_expense(self):
        cmd = parse_command("расход 40 хостинг")
        self.assertEqual(cmd["op"], "expense")
        self.assertEqual(cmd["amount"], Decimal("40.00"))
        self.assertEqual(cmd["comment"], "хостинг")

    def test_topup(self):
        cmd = parse_command("пополни мерча mostbet 100 сетл")
        self.assertEqual(cmd["op"], "delta")
        self.assertEqual(cmd["kind"], "merchant")
        self.assertEqual(cmd["amount"], Decimal("100.00"))

    def test_site_withdraw_default_fee(self):
        cmd = parse_command("вывел с сайта gipay1 1000")
        self.assertEqual(cmd["op"], "site_withdraw")
        self.assertEqual(cmd["username"], "gipay1")
        self.assertEqual(cmd["net"], Decimal("1000.00"))
        self.assertIsNone(cmd["fee"])

    def test_site_withdraw_explicit_fee(self):
        cmd = parse_command("вывел с сайта gipay1 1000 комиссия 5.2")
        self.assertEqual(cmd["op"], "site_withdraw")
        self.assertEqual(cmd["net"], Decimal("1000.00"))
        self.assertEqual(cmd["fee"], Decimal("5.20"))

    def test_site_withdraw_alias(self):
        cmd = parse_command("вывод с сайта payplat1 5000")
        self.assertEqual(cmd["op"], "site_withdraw")
        self.assertEqual(cmd["username"], "payplat1")
        self.assertEqual(cmd["net"], Decimal("5000.00"))


@override_settings(
    CASH_REGISTER_PSP_SITE_WITHDRAWAL_FEE="5",
    CASH_REGISTER_PSP_FREE_WITHDRAWAL="payplat1,prochub1",
)
class AdminBotSiteWithdrawTest(SimpleTestCase):
    def _bal(self, amount: str):
        bal = SimpleNamespace(amount=Decimal(amount))

        def refresh():
            pass

        bal.refresh_from_db = refresh
        return bal

    @patch("payments.admin_bot.transaction.atomic")
    @patch("payments.admin_bot._move")
    @patch("payments.admin_bot._trader_usdt")
    @patch("basics.models.PlatformExpense.objects.create")
    def test_prepaid_psp_books_default_fee(self, create_expense, trader_usdt, move, atomic):
        atomic.return_value.__enter__ = MagicMock(return_value=None)
        atomic.return_value.__exit__ = MagicMock(return_value=False)
        bal = self._bal("2000.00")
        trader_usdt.return_value = (SimpleNamespace(user=SimpleNamespace(username="gipay1")), bal)

        def fake_move(_balance, delta, _comment):
            bal.amount = Decimal(str(bal.amount)) + Decimal(str(delta))

        move.side_effect = fake_move
        reply = _handle_site_withdraw(
            {"op": "site_withdraw", "kind": "trader", "username": "gipay1", "net": Decimal("1000"), "fee": None}
        )
        move.assert_called_once()
        self.assertEqual(move.call_args.args[1], Decimal("-1005.00"))
        create_expense.assert_called_once()
        self.assertEqual(create_expense.call_args.kwargs["amount"], Decimal("5.00"))
        self.assertEqual(bal.amount, Decimal("995.00"))
        self.assertIn("1005", reply)
        self.assertIn("расход 5", reply)

    @patch("payments.admin_bot.transaction.atomic")
    @patch("payments.admin_bot._move")
    @patch("payments.admin_bot._trader_usdt")
    @patch("basics.models.PlatformExpense.objects.create")
    def test_payplat_has_zero_fee(self, create_expense, trader_usdt, move, atomic):
        atomic.return_value.__enter__ = MagicMock(return_value=None)
        atomic.return_value.__exit__ = MagicMock(return_value=False)
        bal = self._bal("8000.00")
        trader_usdt.return_value = (SimpleNamespace(user=SimpleNamespace(username="payplat1")), bal)

        def fake_move(_balance, delta, _comment):
            bal.amount = Decimal(str(bal.amount)) + Decimal(str(delta))

        move.side_effect = fake_move
        reply = _handle_site_withdraw(
            {
                "op": "site_withdraw",
                "kind": "trader",
                "username": "payplat1",
                "net": Decimal("5000"),
                "fee": None,
            }
        )
        self.assertEqual(move.call_args.args[1], Decimal("-5000.00"))
        create_expense.assert_not_called()
        self.assertEqual(bal.amount, Decimal("3000.00"))
        self.assertIn("комиссия 0", reply)

    @patch("payments.admin_bot.transaction.atomic")
    @patch("payments.admin_bot._move")
    @patch("payments.admin_bot._trader_usdt")
    @patch("basics.models.PlatformExpense.objects.create")
    def test_explicit_fee_override(self, create_expense, trader_usdt, move, atomic):
        atomic.return_value.__enter__ = MagicMock(return_value=None)
        atomic.return_value.__exit__ = MagicMock(return_value=False)
        bal = self._bal("2000.00")
        trader_usdt.return_value = (SimpleNamespace(user=SimpleNamespace(username="gipay1")), bal)

        def fake_move(_balance, delta, _comment):
            bal.amount = Decimal(str(bal.amount)) + Decimal(str(delta))

        move.side_effect = fake_move
        _handle_site_withdraw(
            {
                "op": "site_withdraw",
                "kind": "trader",
                "username": "gipay1",
                "net": Decimal("1000"),
                "fee": Decimal("4.80"),
            }
        )
        self.assertEqual(move.call_args.args[1], Decimal("-1004.80"))
        self.assertEqual(create_expense.call_args.kwargs["amount"], Decimal("4.80"))
        self.assertEqual(bal.amount, Decimal("995.20"))
