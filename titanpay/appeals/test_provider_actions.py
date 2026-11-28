import uuid

from django.test import SimpleTestCase

from appeals.provider_actions import (
    merchant_info_text,
    merchant_reject_text,
    parse_provider_callback,
    provider_keyboard,
    restored_provider_text,
)


class _PayIn:
    def __init__(self, merchant_order_id, payin_id="pay-in"):
        self.merchant_order_id = merchant_order_id
        self.id = payin_id


class ProviderActionTextTest(SimpleTestCase):
    def test_keyboard_callbacks_fit_telegram(self):
        appeal_id = uuid.uuid4()
        keyboard = provider_keyboard(appeal_id)
        buttons = [button for row in keyboard["inline_keyboard"] for button in row]
        self.assertEqual(
            [button["text"] for button in buttons],
            ["Подтвердить", "Отклонить", "Запросить доп информацию"],
        )
        for button in buttons:
            self.assertLessEqual(len(button["callback_data"].encode()), 64)
        action, parsed_id = parse_provider_callback(buttons[1]["callback_data"])
        self.assertEqual(action, "reject")
        self.assertEqual(parsed_id, appeal_id)

    def test_unknown_callback(self):
        self.assertIsNone(parse_provider_callback("nope"))
        self.assertIsNone(parse_provider_callback("ap:y:not-a-uuid"))

    def test_merchant_messages_use_merchant_order_id(self):
        pay_in = _PayIn("23213959707")
        self.assertEqual(
            merchant_reject_text(pay_in, "чек не тот"),
            "23213959707\nСтатус: отклонено\nПричина: чек не тот",
        )
        self.assertEqual(
            merchant_reject_text(pay_in, ""),
            "23213959707\nСтатус: отклонено",
        )
        self.assertEqual(
            merchant_info_text(pay_in),
            "Запрос доп информации\n23213959707",
        )
        self.assertEqual(
            restored_provider_text("provider-id", "чек не тот"),
            "provider-id\n\nПричина отклонения: чек не тот",
        )
        self.assertEqual(
            restored_provider_text("provider-id", ""),
            "provider-id\n\nОтклонено (без указания причины)",
        )

    def test_empty_merchant_order_id_falls_back_to_pay_in(self):
        pay_in = _PayIn("", payin_id="11111111-1111-1111-1111-111111111111")
        self.assertIn("11111111-1111-1111-1111-111111111111", merchant_info_text(pay_in))
