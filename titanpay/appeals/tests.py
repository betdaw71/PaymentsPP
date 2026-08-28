from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from appeals.id_resolve import (
    is_merchant_appeal_ticket,
    parse_appeal_ticket,
    resolve_pay_in_from_message,
)
from basics.models import Currency, PaymentSystem
from merchant.models import Merchant
from payments.models import PayIn, PayInStatus

MELBET_TICKET = """
🎟 Тикет #6620b1cb
💰 Депозит
📜 Заказ: 22924514129
👤 Юзер: 1764357337
💰 Сумма: 50 000 KZT
📅 Дата: 10.08.2026 14:01:34
🔗 Номер в ПС:
💡 Маска юзера:
🎯 Реквизиты из заявки:

Статус: ❌ Неуспешно завершено
💬 Комментарий: [AvaPay Manager] Не наш реквизит
""".strip()


class MelbetTicketParseTest(SimpleTestCase):
    def test_extracts_order_and_ticket_hex(self):
        hints = parse_appeal_ticket(MELBET_TICKET)
        self.assertEqual(hints.merchant_order_ids, ["22924514129"])
        self.assertEqual(hints.ticket_hexes, ["6620b1cb"])
        self.assertTrue(is_merchant_appeal_ticket(MELBET_TICKET))

    def test_plain_chat_is_not_a_ticket(self):
        self.assertFalse(is_merchant_appeal_ticket("привет, чек во вложении"))
        self.assertFalse(parse_appeal_ticket("привет").has_ids)


class MelbetTicketResolveTest(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="melbet", password="x")
        self.merchant = Merchant.objects.create(user=user)
        currency = Currency.objects.create(symbol="KZT", name="Tenge")
        ps = PaymentSystem.objects.create(name="C2CKZT", currency=currency, required_fields={})
        self.status = PayInStatus.objects.create(name="Failed")
        self.pay_in = PayIn.objects.create(
            amount=Decimal("50000"),
            currency=currency,
            payment_system=ps,
            merchant_order_id="22924514129",
            callback_url="https://example.com/cb",
            merchant=self.merchant,
            status=self.status,
        )

    def test_resolves_melbet_ticket_by_order_id(self):
        result = resolve_pay_in_from_message(MELBET_TICKET)
        self.assertTrue(result.ok)
        self.assertTrue(result.recognized)
        self.assertEqual(result.pay_in.id, self.pay_in.id)

    def test_resolves_by_short_ticket_hex(self):
        hex8 = str(self.pay_in.id).replace("-", "")[:8]
        result = resolve_pay_in_from_message(f"🎟 Тикет #{hex8}\n💰 Депозит")
        self.assertTrue(result.ok)
        self.assertEqual(result.pay_in.id, self.pay_in.id)

    def test_missing_order_is_recognized_not_found(self):
        result = resolve_pay_in_from_message(
            MELBET_TICKET.replace("22924514129", "00000000000")
        )
        self.assertFalse(result.ok)
        self.assertTrue(result.recognized)
        self.assertEqual(result.error_code, "not_found")

    def test_unrelated_text_has_no_id(self):
        result = resolve_pay_in_from_message("отправьте чек пожалуйста")
        self.assertFalse(result.ok)
        self.assertFalse(result.recognized)
        self.assertEqual(result.error_code, "no_id")
