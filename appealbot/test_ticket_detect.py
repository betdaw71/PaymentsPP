import unittest

from ticket_detect import (
    env_flag,
    extract_cx_slash_uuids,
    extract_uuids,
    generic_receipt_name,
    inline_button_action,
    is_followup_chatter,
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

    def test_watch_sender_allows_humans_for_mostbet_cx(self):
        self.assertTrue(
            should_watch_sender(
                is_self=False,
                is_bot=False,
                username="CSSUP13",
                allowed_usernames=set(),
                allow_humans=True,
            )
        )
        self.assertFalse(
            should_watch_sender(
                is_self=False,
                is_bot=False,
                username="CSSUP13",
                allowed_usernames=set(),
                allow_humans=False,
            )
        )

    def test_cx_mostbet_slash_line_looks_like_ticket(self):
        self.assertTrue(
            looks_like_ticket(
                "9020b2c9-8486-4002-87de-877a7250abad / 1169530557 / 49817737 / 7245350"
            )
        )
        self.assertTrue(
            looks_like_ticket(
                "697c0586-2f22-40b7-a3e8-8413b12d6024 / 1180202470 / 285708868 / 8843400 VIP"
            )
        )
        self.assertEqual(
            extract_cx_slash_uuids(
                "9020b2c9-8486-4002-87de-877a7250abad / 1169530557 / 49817737 / 7245350"
            ),
            ["9020b2c9-8486-4002-87de-877a7250abad"],
        )
        self.assertEqual(
            extract_uuids(
                "235287f6-5582-48ea-83fc-21ef4b0400d5 \\ 1172258283\\ 262337108 | 7660220\n"
                "Any news, colleagues?"
            ),
            ["235287f6-5582-48ea-83fc-21ef4b0400d5"],
        )

    def test_followup_chatter_mostbet_cx(self):
        self.assertTrue(is_followup_chatter("any news?"))
        self.assertTrue(is_followup_chatter("any update ?"))
        self.assertTrue(is_followup_chatter("Does the receipt belong to you?"))
        self.assertTrue(is_followup_chatter("Any news, colleagues?"))
        self.assertFalse(
            is_followup_chatter(
                "9020b2c9-8486-4002-87de-877a7250abad / 1169530557 / 49817737 / 7245350"
            )
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

    def test_pdf_with_uuid_caption_is_not_a_ticket_file(self):
        from ticket_detect import looks_like_ticket_document

        # Pandapay/ops: bank PDF + order UUID in caption must stay a receipt.
        self.assertFalse(
            looks_like_ticket_document(
                "application/pdf",
                "1907326a-9c20-41e9-8a87-d59e8315da99.pdf",
                "1907326a-9c20-41e9-8a87-d59e8315da99",
            )
        )
        self.assertTrue(
            looks_like_ticket_document("application/pdf", "Melbet_ticket.pdf", "anything")
        )

    def test_melbet_caption_does_not_hide_hash_named_receipt(self):
        from ticket_detect import attachment_is_ticket_file, looks_like_ticket

        caption = (
            "Тикет #bd31adc3\n"
            "Заказ: 24781441961\n"
            "Номер в ПС:\n"
            "74f6a81b-040a-4280-865b-75473180\n"
            "f76f"
        )
        self.assertTrue(looks_like_ticket(caption))
        self.assertFalse(
            attachment_is_ticket_file(
                "application/pdf",
                "1d7cee2e863c3f3dd5e99351.pdf",
                caption,
            )
        )
        self.assertTrue(
            attachment_is_ticket_file("application/pdf", "Melbet_ticket.pdf", caption)
        )


if __name__ == "__main__":
    unittest.main()
