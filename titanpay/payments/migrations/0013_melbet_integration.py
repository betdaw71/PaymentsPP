# Generated manually for Melbet typical integration

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0012_playments_sessions"),
    ]

    operations = [
        migrations.AddField(
            model_name="payin",
            name="pending_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="MelbetIntegrationConfig",
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
                ("public_key", models.CharField(db_index=True, max_length=128, unique=True)),
                ("secret_key", models.CharField(max_length=128)),
                ("active", models.BooleanField(default=True)),
                ("whitelist_on", models.BooleanField(default=False)),
                ("whitelist_ips", models.JSONField(blank=True, default=list)),
                ("method_map", models.JSONField(blank=True, default=dict)),
                ("default_ftd", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "merchant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="melbet_integration",
                        to="merchant.merchant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Melbet integration",
                "verbose_name_plural": "Melbet integrations",
            },
        ),
        migrations.CreateModel(
            name="MelbetTransactionSession",
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
                ("order_id", models.CharField(db_index=True, max_length=255)),
                ("melbet_method", models.CharField(blank=True, default="", max_length=64)),
                ("account_number", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "config",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessions",
                        to="payments.melbetintegrationconfig",
                    ),
                ),
                (
                    "pay_in",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="melbet_session",
                        to="payments.payin",
                    ),
                ),
                (
                    "pay_out",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="melbet_session",
                        to="payments.payout",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="melbettransactionsession",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("pay_in__isnull", False),
                    ("pay_out__isnull", True),
                )
                | models.Q(
                    ("pay_in__isnull", True),
                    ("pay_out__isnull", False),
                ),
                name="melbet_session_payin_xor_payout",
            ),
        ),
        migrations.AddConstraint(
            model_name="melbettransactionsession",
            constraint=models.UniqueConstraint(
                fields=("config", "order_id"),
                name="melbet_session_config_order_id",
            ),
        ),
    ]
