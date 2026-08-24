import uuid

from django.db import models

from merchant.models import Merchant


class AppealCounterpartyRole(models.TextChoices):
    MERCHANT = "merchant", "Merchant"
    PROVIDER = "provider", "Provider"


class AppealCounterparty(models.Model):
    """Контрагент апелляций (мерчант или провайдер), инициализация чата по UUID."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=128)
    role = models.CharField(max_length=16, choices=AppealCounterpartyRole.choices)
    merchant = models.ForeignKey(
        to=Merchant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appeal_counterparties",
    )
    psp_provider = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Ключ PSP (botonpay, bitzone, …) для провайдерских чатов",
    )
    trader_username = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Локальный трейдер (если не PSP), например kzt_c2c_test",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Appeal counterparties"

    def __str__(self):
        return f"{self.name} ({self.role})"


class AppealTelegramChat(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    counterparty = models.ForeignKey(
        to=AppealCounterparty,
        on_delete=models.CASCADE,
        related_name="telegram_chats",
    )
    telegram_chat_id = models.BigIntegerField(unique=True)
    title = models.CharField(max_length=255, blank=True, default="")
    registered_by_username = models.CharField(max_length=128, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title or self.telegram_chat_id} -> {self.counterparty.name}"


class PayInAppealSource(models.TextChoices):
    TELEGRAM_MERCHANT = "telegram_merchant", "Telegram merchant group"
    PAYMENT_PAGE = "payment_page", "Payment page"
    SYSTEM = "system", "System"


class PayInAppealStatus(models.TextChoices):
    CREATED = "created", "Created"
    SENT_TO_PROVIDER = "sent_to_provider", "Sent to provider"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    DUPLICATE = "duplicate", "Duplicate"
    FAILED = "failed", "Failed"
    NO_PROVIDER_CHAT = "no_provider_chat", "No provider chat"


class PayInAppeal(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.ForeignKey(to="payments.PayIn", on_delete=models.CASCADE, related_name="appeals")
    in_order = models.ForeignKey(
        to="trade.InOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appeals",
    )
    source_counterparty = models.ForeignKey(
        to=AppealCounterparty,
        on_delete=models.SET_NULL,
        null=True,
        related_name="source_appeals",
    )
    source = models.CharField(max_length=32, choices=PayInAppealSource.choices)
    receipt_url = models.URLField(max_length=1024, blank=True, default="")
    status = models.CharField(max_length=32, choices=PayInAppealStatus.choices, default=PayInAppealStatus.CREATED)
    psp_provider = models.CharField(max_length=32, blank=True, default="")
    provider_external_id = models.CharField(max_length=255, blank=True, default="")
    provider_chat_id = models.BigIntegerField(null=True, blank=True)
    provider_message_id = models.BigIntegerField(null=True, blank=True)
    source_telegram_chat_id = models.BigIntegerField(null=True, blank=True)
    source_telegram_message_id = models.BigIntegerField(null=True, blank=True)
    error_message = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["pay_in", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Appeal {self.id} pay_in={self.pay_in_id}"
