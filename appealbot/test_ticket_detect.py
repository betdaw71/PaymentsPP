import unittest

from ticket_detect import (
    env_flag,
    generic_receipt_name,
    inline_button_action,
    looks_like_ticket,
    parse_int_ids,
    parse_usernames,
    should_watch_sender,
)


class TicketDetectTest(unittest.TestCase):
    def test_mel_transaction_bot_caption(self):
        text = (
            "🎟 Тикет #15b236c8\n"
            "📜 Заказ: 23213959707\n"
            "🔗 Номер в ПС: 6f705f1b-229b-4539-9c1c-966199da2567"
        )
        self.assertTrue(looks_like_ticket(text))

    def test_plain_chat_is_ignored(self):
        self.assertFalse(looks_like_ticket("привет"))
        self.assertFalse(looks_like_ticket("Успех"))

    def test_inline_buttons(self):
        self.assertEqual(inline_button_action("✅ Подтвердить"), "approve")
        self.assertEqual(inline_button_action("❌ Отклонить"), "reject")
        self.assertIsNone(inline_button_action("📄 Запросить доп информацию"))
        self.assertIsNone(inline_button_action("что-то ещё"))

    def test_watch_sender_defaults_to_bots_only(self):
        self.assertTrue(
            should_watch_sender(is_self=False, is_bot=True, username="MelTransactionBot", allowed_usernames=set())
        )
        self.assertFalse(
            should_watch_sender(is_self=False, is_bot=False, username="support", allowed_usernames=set())
        )
        self.assertFalse(
            should_watch_sender(is_self=True, is_bot=True, username="MelTransactionBot", allowed_usernames=set())
        )

    def test_watch_sender_username_allowlist(self):
        allowed = {"meltransactionbot"}
        self.assertTrue(
            should_watch_sender(
                is_self=False,
                is_bot=True,
                username="MelTransactionBot",
                allowed_usernames=allowed,
            )
        )
        self.assertFalse(
            should_watch_sender(
                is_self=False,
                is_bot=True,
                username="some_other_bot",
                allowed_usernames=allowed,
            )
        )

    def test_parsers(self):
        self.assertEqual(parse_int_ids("-100123, 456;abc"), {-100123, 456})
        self.assertEqual(parse_usernames("@MelTransactionBot, other"), {"meltransactionbot", "other"})
        self.assertTrue(env_flag("1"))
        self.assertFalse(env_flag("0"))

    def test_receipt_name_from_magic(self):
        self.assertEqual(generic_receipt_name("Melbet_ticket.pdf", b"%PDF-1.4"), "receipt.pdf")
        self.assertEqual(generic_receipt_name("x.bin", b"\xff\xd8\xff\x00"), "receipt.jpg")

    def test_album_captions_merge_for_id(self):
        """Caption may sit on a later album item — combined text must still look like a ticket."""
        first = "фото чека"
        second = "Заказ: 23213959707\n6f705f1b-229b-4539-9c1c-966199da2567"
        combined = f"{first}\n{second}"
        self.assertTrue(looks_like_ticket(combined))
        self.assertFalse(looks_like_ticket(first))


if __name__ == "__main__":
    unittest.main()
