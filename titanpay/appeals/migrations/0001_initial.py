import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("merchant", "0006_merchant_balance_kzt"),
        ("payments", "0019_botonpay_pay_in_session"),
        ("trade", "0006_agent_fee_db_default"),
    ]

    operations = [
        migrations.CreateModel(
            name="AppealCounterparty",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("name", models.CharField(max_length=128)),
                (
                    "role",
                    models.CharField(
                        choices=[("merchant", "Merchant"), ("provider", "Provider")],
                        max_length=16,
                    ),
                ),
                (
                    "psp_provider",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Ключ PSP (botonpay, bitzone, …) для провайдерских чатов",
                        max_length=32,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "merchant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="appeal_counterparties",
                        to="merchant.merchant",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Appeal counterparties",
            },
        ),
        migrations.CreateModel(
            name="AppealTelegramChat",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("telegram_chat_id", models.BigIntegerField(unique=True)),
                ("title", models.CharField(blank=True, default="", max_length=255)),
                (
                    "registered_by_username",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "counterparty",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="telegram_chats",
                        to="appeals.appealcounterparty",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PayInAppeal",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("telegram_merchant", "Telegram merchant group"),
                            ("payment_page", "Payment page"),
                            ("system", "System"),
                        ],
                        max_length=32,
                    ),
                ),
                ("receipt_url", models.URLField(blank=True, default="", max_length=1024)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("sent_to_provider", "Sent to provider"),
                            ("duplicate", "Duplicate"),
                            ("failed", "Failed"),
                            ("no_provider_chat", "No provider chat"),
                        ],
                        default="created",
                        max_length=32,
                    ),
                ),
                ("psp_provider", models.CharField(blank=True, default="", max_length=32)),
                (
                    "provider_external_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("provider_chat_id", models.BigIntegerField(blank=True, null=True)),
                ("provider_message_id", models.BigIntegerField(blank=True, null=True)),
                ("source_telegram_chat_id", models.BigIntegerField(blank=True, null=True)),
                ("source_telegram_message_id", models.BigIntegerField(blank=True, null=True)),
                ("error_message", models.CharField(blank=True, default="", max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "in_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="appeals",
                        to="trade.inorder",
                    ),
                ),
                (
                    "pay_in",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="appeals",
                        to="payments.payin",
                    ),
                ),
                (
                    "source_counterparty",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_appeals",
                        to="appeals.appealcounterparty",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["pay_in", "created_at"], name="appeals_pay_created_idx"),
                    models.Index(fields=["status", "created_at"], name="appeals_status_created_idx"),
                ],
            },
        ),
    ]
