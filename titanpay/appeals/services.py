from __future__ import annotations

import uuid
from dataclasses import dataclass
from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import transaction

from appeals.id_resolve import resolve_pay_in_from_message
from appeals.models import (
    AppealCounterparty,
    AppealCounterpartyRole,
    AppealTelegramChat,
    PayInAppeal,
    PayInAppealSource,
    PayInAppealStatus,
)
from appeals.provider_privacy import (
    extract_pdf_text,
    is_merchant_ticket_file,
    provider_safe_caption,
    provider_safe_filename,
)
from payments.psp_payin import _psp_provider_for_trader, psp_external_reference
from payments.utils import upload_receipt_storage


@dataclass
class AppealProcessResult:
    ok: bool
    message: str
    recognized: bool = False
    outcome: str = "rejected"  # success | rejected | partial | pending | await_receipt


def _reject(message: str, *, recognized: bool = False) -> AppealProcessResult:
    return AppealProcessResult(ok=False, message=message, recognized=recognized, outcome="rejected")


def _success(message: str, *, recognized: bool = True) -> AppealProcessResult:
    return AppealProcessResult(ok=True, message=message, recognized=recognized, outcome="success")


def _partial(message: str, *, recognized: bool = True) -> AppealProcessResult:
    return AppealProcessResult(ok=True, message=message, recognized=recognized, outcome="partial")


def _pending(message: str, *, recognized: bool = True) -> AppealProcessResult:
    return AppealProcessResult(ok=True, message=message, recognized=recognized, outcome="pending")


def _await_receipt(message: str, *, recognized: bool = True) -> AppealProcessResult:
    return AppealProcessResult(ok=False, message=message, recognized=recognized, outcome="await_receipt")


def get_chat_counterparty(chat_id: int) -> AppealTelegramChat | None:
    return (
        AppealTelegramChat.objects.filter(telegram_chat_id=chat_id, is_active=True)
        .select_related("counterparty", "counterparty__merchant")
        .first()
    )


def init_telegram_chat(
    *,
    counterparty_id: str,
    chat_id: int,
    title: str = "",
    registered_by_username: str = "",
) -> tuple[bool, str]:
    try:
        counterparty = AppealCounterparty.objects.get(id=counterparty_id, is_active=True)
    except AppealCounterparty.DoesNotExist:
        return False, "Контрагент с таким UUID не найден или неактивен."

    chat, created = AppealTelegramChat.objects.update_or_create(
        telegram_chat_id=chat_id,
        defaults={
            "counterparty": counterparty,
            "title": title or "",
            "registered_by_username": registered_by_username or "",
            "is_active": True,
        },
    )
    action = "зарегистрирован" if created else "обновлён"
    role_label = "мерчант" if counterparty.role == AppealCounterpartyRole.MERCHANT else "провайдер"
    return True, f"Чат {action} как {role_label}: {counterparty.name} ({counterparty.id})."


def _trader_for_order(order):
    if not order or not order.payment_details_id:
        return None
    details = order.payment_details
    if not details or not details.group_id:
        return None
    return details.group.trader


def _trader_username_for_pay_in(pay_in) -> str:
    trader = _trader_for_order(pay_in.order)
    if not trader or not getattr(trader, "user", None):
        return ""
    return trader.user.username or ""


def _psp_provider_for_pay_in(pay_in) -> str:
    trader = _trader_for_order(pay_in.order)
    if not trader:
        return ""
    provider_key, _ = _psp_provider_for_trader(trader)
    return provider_key or ""


def _provider_chat(*, psp_provider: str, trader_username: str = "") -> AppealTelegramChat | None:
    if trader_username:
        chat = (
            AppealTelegramChat.objects.filter(
                is_active=True,
                counterparty__role=AppealCounterpartyRole.PROVIDER,
                counterparty__trader_username=trader_username,
                counterparty__is_active=True,
            )
            .select_related("counterparty")
            .first()
        )
        if chat:
            return chat

    if not psp_provider:
        return None
    return (
        AppealTelegramChat.objects.filter(
            is_active=True,
            counterparty__role=AppealCounterpartyRole.PROVIDER,
            counterparty__psp_provider=psp_provider,
            counterparty__is_active=True,
        )
        .select_related("counterparty")
        .first()
    )


def _provider_caption(*, pay_in, psp_provider: str, provider_external_id: str) -> str:
    if psp_provider == "botonpay" and provider_external_id:
        return provider_external_id
    if psp_provider == "payplat":
        # PayPlat сверяет апелляции по shop_internal_id (= id PayIn)
        return str(pay_in.id)
    if provider_external_id:
        return provider_external_id
    return str(pay_in.id)


def _upload_receipt(file_bytes: bytes, pay_in_id: str, filename: str) -> str:
    ext = "jpg"
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()[:8] or "jpg"
    short_id = str(pay_in_id).replace("-", "")[:12]
    object_name = f"appeals/{short_id}-{uuid.uuid4().hex[:10]}.{ext}"
    return upload_receipt_storage(BytesIO(file_bytes), object_name)


def _save_order_pic(order, receipt_url: str) -> None:
    if not order or not receipt_url:
        return
    if len(receipt_url) > 200:
        return
    try:
        order.pic = receipt_url
        order.save(update_fields=["pic"])
    except ValidationError:
        pass


def _try_order_arbitrage(order) -> None:
    if order is None:
        return
    status_name = order.status.name
    try:
        if status_name in {"Cancelled", "Expired", "Cancelled by support", "Cancelled by trader"}:
            order.arbitrage()
        elif status_name in {"Money sent by user", "New"}:
            order.arbitrage_expired()
    except ValidationError:
        pass


def _psp_meta_for_pay_in(pay_in):
    ext = psp_external_reference(pay_in) or {}
    psp_provider = ext.get("psp_provider") or _psp_provider_for_pay_in(pay_in)
    trader_username = _trader_username_for_pay_in(pay_in)
    provider_external_id = ext.get("psp_provider_order_id") or ""
    return psp_provider, trader_username, provider_external_id


def _forward_appeal_to_provider(
    *,
    appeal: PayInAppeal,
    pay_in,
    file_bytes: bytes,
    filename: str,
    psp_provider: str,
    provider_external_id: str,
    trader_username: str,
) -> AppealProcessResult:
    provider_chat = _provider_chat(psp_provider=psp_provider, trader_username=trader_username)
    if provider_chat is None:
        appeal.status = PayInAppealStatus.NO_PROVIDER_CHAT
        appeal.error_message = (
            f"Нет Telegram-чата провайдера для PSP={psp_provider or '—'}, "
            f"trader={trader_username or '—'}"
        )
        appeal.save(update_fields=["status", "error_message"])
        return _partial(
            f"Апелляция создана (ID {appeal.id}), но чат провайдера не настроен "
            f"({psp_provider or trader_username or 'локальный трейдер'})."
        )

    from appeals.telegram_out import send_receipt_to_provider_chat

    if is_merchant_ticket_file(filename=filename, file_bytes=file_bytes):
        appeal.status = PayInAppealStatus.FAILED
        appeal.error_message = "Отклонён тикет мерчанта: провайдеру отправляется только чек"
        appeal.save(update_fields=["status", "error_message"])
        return _reject(
            "Это тикет мерчанта, а не чек. Пришлите фото или PDF квитанции из банка.",
            recognized=True,
        )

    raw_caption = _provider_caption(
        pay_in=pay_in,
        psp_provider=psp_provider,
        provider_external_id=provider_external_id,
    )
    caption = provider_safe_caption(
        raw_caption,
        fallback=str(pay_in.id),
        pay_in=pay_in,
    )
    safe_name = provider_safe_filename(filename, file_bytes)
    sent = send_receipt_to_provider_chat(
        chat_id=provider_chat.telegram_chat_id,
        file_bytes=file_bytes,
        filename=safe_name,
        caption=caption,
    )
    if not sent.ok:
        appeal.status = PayInAppealStatus.FAILED
        appeal.error_message = sent.error or "Не удалось отправить в чат провайдера"
        appeal.save(update_fields=["status", "error_message"])
        return _partial(f"Апелляция создана, но не отправлена провайдеру: {sent.error}")

    appeal.status = PayInAppealStatus.SENT_TO_PROVIDER
    appeal.provider_chat_id = provider_chat.telegram_chat_id
    appeal.provider_message_id = sent.message_id
    appeal.save(update_fields=["status", "provider_chat_id", "provider_message_id"])
    return _pending("Апелляция принята, ожидаем подтверждения.")


@transaction.atomic
def process_payment_page_receipt(
    *,
    pay_in,
    file_bytes: bytes,
    filename: str,
) -> AppealProcessResult:
    if not file_bytes:
        return _reject("Прикрепите чек (фото или файл).")

    order = pay_in.order
    if order is None:
        return _reject("Заявка без ордера.", recognized=True)

    if order.status.name not in {"New", "Money sent by user"}:
        return _reject("Неверный статус заявки.", recognized=True)

    if PayInAppeal.objects.filter(
        pay_in=pay_in,
        status__in=[
            PayInAppealStatus.CREATED,
            PayInAppealStatus.SENT_TO_PROVIDER,
        ],
    ).exists():
        return _pending("Чек уже отправлен.")

    try:
        receipt_url = _upload_receipt(file_bytes, str(pay_in.id), filename or "receipt")
    except Exception as exc:
        return _reject(f"Не удалось сохранить чек: {exc}", recognized=True)

    _save_order_pic(order, receipt_url)

    psp_provider, trader_username, provider_external_id = _psp_meta_for_pay_in(pay_in)
    appeal = PayInAppeal.objects.create(
        pay_in=pay_in,
        in_order=order,
        source=PayInAppealSource.PAYMENT_PAGE,
        receipt_url=receipt_url,
        status=PayInAppealStatus.CREATED,
        psp_provider=psp_provider or "",
        provider_external_id=provider_external_id,
    )
    return _forward_appeal_to_provider(
        appeal=appeal,
        pay_in=pay_in,
        file_bytes=file_bytes,
        filename=provider_safe_filename(filename, file_bytes),
        psp_provider=psp_provider,
        provider_external_id=provider_external_id,
        trader_username=trader_username,
    )


def _combined_ticket_text(
    text: str,
    *,
    file_bytes: bytes,
    filename: str,
    ticket_file_bytes: bytes | None,
) -> tuple[str, bool]:
    """Merge captions with PDF ticket text. Returns (text, uploaded_file_is_ticket)."""
    parts = [text or ""]
    file_is_ticket = is_merchant_ticket_file(filename=filename, file_bytes=file_bytes)
    if ticket_file_bytes:
        extracted = extract_pdf_text(ticket_file_bytes)
        if extracted:
            parts.append(extracted)
    if file_is_ticket and file_bytes.startswith(b"%PDF"):
        extracted = extract_pdf_text(file_bytes)
        if extracted:
            parts.append(extracted)
    combined = "\n".join(part.strip() for part in parts if part and part.strip())
    return combined, file_is_ticket


@transaction.atomic
def process_merchant_appeal_message(
    *,
    chat_id: int,
    message_id: int,
    text: str,
    file_bytes: bytes,
    filename: str,
    ticket_file_bytes: bytes | None = None,
) -> AppealProcessResult:
    chat = get_chat_counterparty(chat_id)
    if chat is None:
        return _reject("Чат не зарегистрирован. Выполните /init <uuid контрагента>.")
    counterparty = chat.counterparty
    if counterparty.role != AppealCounterpartyRole.MERCHANT:
        return _reject("Этот чат зарегистрирован как провайдерский. Апелляции принимаются только из чата мерчанта.")

    if not file_bytes:
        return _reject("Прикрепите чек (фото или файл).")

    combined_text, file_is_ticket = _combined_ticket_text(
        text,
        file_bytes=file_bytes,
        filename=filename,
        ticket_file_bytes=ticket_file_bytes,
    )
    if file_is_ticket:
        resolved_ticket = resolve_pay_in_from_message(combined_text)
        if resolved_ticket.ok:
            return _await_receipt(
                "Тикет распознан. Пришлите чек (фото квитанции из банка). "
                "Сам тикет провайдеру не отправляется."
            )
        if resolved_ticket.recognized:
            return _reject(resolved_ticket.error_message, recognized=True)
        return _await_receipt(
            "Похоже на тикет мерчанта, а не на чек. Ответьте на тикет фото квитанции "
            "или отправьте /appeal ответом на тикет, затем чек."
        )

    resolved = resolve_pay_in_from_message(combined_text)
    if not resolved.ok:
        return _reject(resolved.error_message, recognized=resolved.recognized)

    pay_in = resolved.pay_in
    if counterparty.merchant_id and pay_in.merchant_id != counterparty.merchant_id:
        return _reject("Заявка не относится к этому мерчанту.", recognized=True)

    if PayInAppeal.objects.filter(
        pay_in=pay_in,
        status__in=[
            PayInAppealStatus.CREATED,
            PayInAppealStatus.SENT_TO_PROVIDER,
        ],
    ).exists():
        return _reject("Апелляция по этой заявке уже создана.", recognized=True)

    try:
        receipt_url = _upload_receipt(file_bytes, str(pay_in.id), filename or "receipt")
    except Exception as exc:
        return _reject(f"Не удалось сохранить чек: {exc}", recognized=True)

    order = pay_in.order
    _save_order_pic(order, receipt_url)

    _try_order_arbitrage(order)

    psp_provider, trader_username, provider_external_id = _psp_meta_for_pay_in(pay_in)

    appeal = PayInAppeal.objects.create(
        pay_in=pay_in,
        in_order=order,
        source_counterparty=counterparty,
        source=PayInAppealSource.TELEGRAM_MERCHANT,
        receipt_url=receipt_url,
        status=PayInAppealStatus.CREATED,
        psp_provider=psp_provider or "",
        provider_external_id=provider_external_id,
        source_telegram_chat_id=chat_id,
        source_telegram_message_id=message_id,
    )

    return _forward_appeal_to_provider(
        appeal=appeal,
        pay_in=pay_in,
        file_bytes=file_bytes,
        filename=provider_safe_filename(filename, file_bytes),
        psp_provider=psp_provider,
        provider_external_id=provider_external_id,
        trader_username=trader_username,
    )
