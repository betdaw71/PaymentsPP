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

    def test_live_melbet_ticket_with_nbsp_amount(self):
        ticket = (
            "🎟 Тикет #15b236c8\n"
            "💰 Депозит\n"
            "📜 Заказ: 23213959707\n"
            "👤 Юзер: 1784701431\n"
            "💰 Сумма: 11\u00a0431 KZT\n"
            "📅 Дата: 29.08.2026 14:51:55\n"
            "🔗 Номер в ПС: 6f705f1b-229b-4539-9c1c-966199da2567\n"
            "💡 Маска юзера:\n"
            "🎯 Реквизиты из заявки:\n"
            "\n"
            "Статус: 🆕 Создан\n"
            "💬 Комментарий: Не пришел депозит"
        )
        hints = parse_appeal_ticket(ticket)
        self.assertEqual(hints.merchant_order_ids, ["23213959707"])
        self.assertEqual(hints.ticket_hexes, ["15b236c8"])
        self.assertEqual(hints.psp_ids, ["6f705f1b-229b-4539-9c1c-966199da2567"])
        self.assertTrue(is_merchant_appeal_ticket(ticket))


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

    def test_screenshot_ticket_with_psp_uuid(self):
        ticket = """
🎟 Тикет #02f6868c
💰 Депозит
📜 Заказ: 23199289573
👤 Юзер: 1669608479
💰 Сумма: 15 000 KZT
📅 Дата: 28.08.2026 18:49:42
🔗 Номер в ПС: 77334ffa-2b2d-4509-aedc-d9437076efcf
💡 Маска юзера:
🎯 Реквизиты из заявки:
Статус: 🆕 Создан
💬 Комментарий: Не пришел депозит
""".strip()
        self.pay_in.merchant_order_id = "23199289573"
        self.pay_in.save(update_fields=["merchant_order_id"])
        result = resolve_pay_in_from_message(ticket)
        self.assertTrue(result.ok)
        self.assertEqual(result.pay_in.id, self.pay_in.id)

    def test_gps_label_is_parsed(self):
        from appeals.id_resolve import parse_appeal_ticket

        hints = parse_appeal_ticket("🔗 Номер в ГПС: abc-123-xyz")
        self.assertEqual(hints.psp_ids, ["abc-123-xyz"])

    def test_order_id_on_next_line(self):
        wrapped = "📜 Заказ:\n22924514129\n🎟 Тикет №6620b1cb"
        hints = parse_appeal_ticket(wrapped)
        self.assertEqual(hints.merchant_order_ids, ["22924514129"])
        self.assertEqual(hints.ticket_hexes, ["6620b1cb"])
        result = resolve_pay_in_from_message(wrapped)
        self.assertTrue(result.ok)
        self.assertEqual(result.pay_in.id, self.pay_in.id)


class ProviderPrivacyTest(SimpleTestCase):
    def test_filename_never_keeps_merchant_brand(self):
        from appeals.provider_privacy import provider_safe_filename

        jpeg = b"\xff\xd8\xff" + b"\x00" * 32
        self.assertEqual(provider_safe_filename("Melbet_ticket.JPG", jpeg), "receipt.jpg")
        self.assertEqual(provider_safe_filename("Melbet_Deposit.pdf", b"%PDF-1.4 x"), "receipt.pdf")

    def test_caption_strips_melbet_and_avapay(self):
        from appeals.provider_privacy import provider_safe_caption

        fallback = "77334ffa-2b2d-4509-aedc-d9437076efcf"
        self.assertEqual(provider_safe_caption("Melbet", fallback=fallback), fallback)
        self.assertEqual(provider_safe_caption("AvaPay Manager", fallback=fallback), fallback)
        self.assertEqual(
            provider_safe_caption("Melbet ticket #6620b1cb\nЗаказ: 1", fallback=fallback),
            fallback,
        )
        self.assertEqual(provider_safe_caption(fallback, fallback=fallback), fallback)

    def test_ticket_pdf_detected_by_text(self):
        from appeals.provider_privacy import extract_pdf_text, is_merchant_ticket_file

        pdf = _ticket_pdf_bytes(MELBET_TICKET)
        self.assertIn("22924514129", extract_pdf_text(pdf))
        self.assertTrue(is_merchant_ticket_file(filename="receipt.pdf", file_bytes=pdf))
        self.assertTrue(is_merchant_ticket_file(filename="Melbet_6620.pdf", file_bytes=b"%PDF-1.4"))


def _ticket_pdf_bytes(text: str) -> bytes:
    import re

    import fitz

    doc = fitz.open()
    page = doc.new_page()
    # Built-in Helvetica has no Cyrillic; keep ASCII labels so extract_pdf_text is reliable in tests.
    page.insert_text((36, 72), "Melbet ticket")
    order = re.search(r"Заказ:\s*([A-Za-z0-9._-]+)", text)
    if order:
        page.insert_text((36, 96), f"Order ID: {order.group(1)}")
    page.insert_text((36, 120), text[:500])
    data = doc.tobytes()
    doc.close()
    return data


class MerchantAppealForwardTest(TestCase):
    def setUp(self):
        from appeals.models import AppealCounterparty, AppealCounterpartyRole, AppealTelegramChat

        user = User.objects.create_user(username="melbet", password="x")
        self.merchant = Merchant.objects.create(user=user)
        currency = Currency.objects.create(symbol="KZT", name="Tenge")
        ps = PaymentSystem.objects.create(name="C2CKZT", currency=currency, required_fields={})
        status = PayInStatus.objects.create(name="Failed")
        self.pay_in = PayIn.objects.create(
            amount=Decimal("50000"),
            currency=currency,
            payment_system=ps,
            merchant_order_id="22924514129",
            callback_url="https://example.com/cb",
            merchant=self.merchant,
            status=status,
        )
        merchant_cp = AppealCounterparty.objects.create(
            name="Melbet",
            role=AppealCounterpartyRole.MERCHANT,
            merchant=self.merchant,
        )
        self.merchant_cp = merchant_cp
        provider_cp = AppealCounterparty.objects.create(
            name="PayPlat",
            role=AppealCounterpartyRole.PROVIDER,
            psp_provider="payplat",
        )
        AppealTelegramChat.objects.create(
            counterparty=merchant_cp,
            telegram_chat_id=111,
            is_active=True,
        )
        AppealTelegramChat.objects.create(
            counterparty=provider_cp,
            telegram_chat_id=222,
            is_active=True,
        )

    def test_provider_chat_is_skipped_without_reply_text(self):
        from appeals.services import chat_role_for_telegram, process_merchant_appeal_message

        self.assertEqual(chat_role_for_telegram(111), "merchant")
        self.assertEqual(chat_role_for_telegram(222), "provider")
        self.assertEqual(chat_role_for_telegram(999), "unknown")
        result = process_merchant_appeal_message(
            chat_id=222,
            message_id=1,
            text="ответьте на тикет Melbet",
            file_bytes=b"\xff\xd8\xff" + b"\x00" * 16,
            filename="receipt.jpg",
        )
        self.assertEqual(result.outcome, "skip")
        self.assertEqual(result.message, "")

    def test_ticket_pdf_sends_provider_id_not_the_ticket(self):
        from unittest.mock import patch

        from appeals.services import process_merchant_appeal_message
        from appeals.telegram_out import SendResult

        pdf = _ticket_pdf_bytes(MELBET_TICKET)
        with (
            patch(
                "appeals.services._psp_meta_for_pay_in",
                return_value=("payplat", "", str(self.pay_in.id)),
            ),
            patch("appeals.telegram_out.send_receipt_to_provider_chat") as mock_file,
            patch(
                "appeals.telegram_out.send_text_to_provider_chat",
                return_value=SendResult(ok=True, message_id=88),
            ) as mock_text,
        ):
            result = process_merchant_appeal_message(
                chat_id=111,
                message_id=10,
                text="",
                file_bytes=pdf,
                filename="Melbet_ticket.pdf",
            )
        self.assertEqual(result.outcome, "pending")
        self.assertEqual(result.message, "")
        mock_file.assert_not_called()
        kwargs = mock_text.call_args.kwargs
        self.assertEqual(kwargs["text"], str(self.pay_in.id))
        self.assertNotRegex(kwargs["text"], r"(?i)melbet|тикет|заказ")

    def test_text_only_ticket_goes_to_provider_without_merchant_name(self):
        from unittest.mock import patch

        from appeals.services import init_telegram_chat, process_merchant_appeal_message
        from appeals.telegram_out import SendResult

        ok, msg = init_telegram_chat(counterparty_id=str(self.merchant_cp.id), chat_id=333)
        self.assertTrue(ok)
        self.assertNotRegex(msg, r"(?i)melbet")

        live = (
            "🎟 Тикет #15b236c8\n"
            "📜 Заказ: 23213959707\n"
            "🔗 Номер в ПС: 6f705f1b-229b-4539-9c1c-966199da2567\n"
            "🎯 Реквизиты из заявки:\n"
            "💬 Комментарий: Не пришел депозит"
        )
        self.pay_in.merchant_order_id = "23213959707"
        self.pay_in.save(update_fields=["merchant_order_id"])
        with (
            patch(
                "appeals.services._psp_meta_for_pay_in",
                return_value=("payplat", "", str(self.pay_in.id)),
            ),
            patch("appeals.telegram_out.send_receipt_to_provider_chat") as mock_file,
            patch(
                "appeals.telegram_out.send_text_to_provider_chat",
                return_value=SendResult(ok=True, message_id=77),
            ) as mock_text,
        ):
            result = process_merchant_appeal_message(
                chat_id=111,
                message_id=12,
                text=live,
                file_bytes=b"",
                filename="",
            )
        self.assertEqual(result.outcome, "pending")
        self.assertEqual(result.message, "")
        mock_file.assert_not_called()
        self.assertEqual(mock_text.call_args.kwargs["text"], str(self.pay_in.id))
        self.assertNotRegex(mock_text.call_args.kwargs["text"], r"(?i)melbet|payplat")

    def test_receipt_plus_ticket_pdf_forwards_only_safe_payload(self):
        from unittest.mock import patch

        from appeals.services import process_merchant_appeal_message
        from appeals.telegram_out import SendResult

        jpeg = b"\xff\xd8\xff" + b"\x00" * 64
        ticket_pdf = _ticket_pdf_bytes(MELBET_TICKET)
        with (
            patch("appeals.services.upload_receipt_storage", return_value="https://s3/r.jpg"),
            patch(
                "appeals.services._psp_meta_for_pay_in",
                return_value=("payplat", "", str(self.pay_in.id)),
            ),
            patch(
                "appeals.telegram_out.send_receipt_to_provider_chat",
                return_value=SendResult(ok=True, message_id=99),
            ) as mock_send,
        ):
            result = process_merchant_appeal_message(
                chat_id=111,
                message_id=11,
                text="",
                file_bytes=jpeg,
                filename="Melbet_screenshot.jpg",
                ticket_file_bytes=ticket_pdf,
            )
        self.assertEqual(result.outcome, "pending")
        self.assertTrue(result.ok)
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["filename"], "receipt.jpg")
        self.assertEqual(kwargs["file_bytes"], jpeg)
        self.assertNotRegex(kwargs["caption"], r"(?i)melbet|avapay|тикет|заказ")
        self.assertEqual(kwargs["caption"], str(self.pay_in.id))

    def test_send_receipt_rewrites_leaking_filename_and_caption(self):
        from unittest.mock import MagicMock, patch

        from appeals.telegram_out import send_receipt_to_provider_chat

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 7}}
        mock_response.text = ""
        with (
            patch("appeals.telegram_out._bot_token", return_value="token"),
            patch("appeals.telegram_out.requests.post", return_value=mock_response) as mock_post,
        ):
            send_receipt_to_provider_chat(
                chat_id=222,
                file_bytes=b"%PDF-1.4 body",
                filename="Melbet_ticket.pdf",
                caption="Melbet / AvaPay ticket",
            )
        kwargs = mock_post.call_args.kwargs
        self.assertEqual(kwargs["files"]["document"][0], "receipt.pdf")
        self.assertNotRegex(kwargs["data"]["caption"], r"(?i)melbet|avapay")
