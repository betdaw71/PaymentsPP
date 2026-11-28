from decimal import Decimal

from django.test import SimpleTestCase

from payments.admin_bot import parse_command


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

    def test_lookup(self):
        cmd = parse_command("/lookup 3f2a1c0e-1111-2222-3333-444455556666")
        self.assertEqual(cmd["op"], "lookup")
        self.assertIn("3f2a1c0e", cmd["query"])

    def test_lookup_without_id(self):
        self.assertEqual(parse_command("/lookup")["op"], "lookup_help")

    def test_topup(self):
        cmd = parse_command("пополни мерча mostbet 100 сетл")
        self.assertEqual(cmd["op"], "delta")
        self.assertEqual(cmd["kind"], "merchant")
        self.assertEqual(cmd["amount"], Decimal("100.00"))
