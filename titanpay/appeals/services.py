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
from payments.psp_payin import _psp_provider_for_trader, psp_external_reference
from payments.utils import upload_receipt_storage


@dataclass
class AppealProcessResult:
    ok: bool
    message: str
    recognized: bool = False
    outcome: str = "rejected"  # success | rejected | partial | pending


def _reject(message: str, *, recognized: bool = False) -> AppealProcessResult:
    return AppealProcessResult(ok=False, message=message, recognized=recognized, outcome="rejected")


def _success(message: str, *, recognized: bool = True) -> AppealProcessResult:
    return AppealProcessResult(ok=True, message=message, recognized=recognized, outcome="success")


def _partial(message: str, *, recognized: bool = True) -> AppealProcessResult:
    return AppealProcessResult(ok=True, message=message, recognized=recognized, outcome="partial")


def _pending(message: str, *, recognized: bool = True) -> AppealProcessResult:
    return AppealProcessResult(ok=True, message=message, recognized=recognized, outcome="pending")


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
        elif status_name == "Money sent by user":
            order.arbitrage_expired()
    except ValidationError:
        pass


@transaction.atomic
def process_merchant_appeal_message(
    *,
    chat_id: int,
    message_id: int,
    text: str,
    file_bytes: bytes,
    filename: str,
) -> AppealProcessResult:
    chat = get_chat_counterparty(chat_id)
    if chat is None:
        return _reject("Чат не зарегистрирован. Выполните /init <uuid контрагента>.")
    counterparty = chat.counterparty
    if counterparty.role != AppealCounterpartyRole.MERCHANT:
        return _reject("Этот чат зарегистрирован как провайдерский. Апелляции принимаются только из чата мерчанта.")

    if not file_bytes:
        return _reject("Прикрепите чек (фото или файл).")

    resolved = resolve_pay_in_from_message(text or "")
    if not resolved.ok:
        return _reject(resolved.error_message)

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

    ext = psp_external_reference(pay_in) or {}
    psp_provider = ext.get("psp_provider") or _psp_provider_for_pay_in(pay_in)
    trader_username = _trader_username_for_pay_in(pay_in)
    provider_external_id = ext.get("psp_provider_order_id") or ""

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

    caption = _provider_caption(
        pay_in=pay_in,
        psp_provider=psp_provider,
        provider_external_id=provider_external_id,
    )
    sent = send_receipt_to_provider_chat(
        chat_id=provider_chat.telegram_chat_id,
        file_bytes=file_bytes,
        filename=filename or "receipt",
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
