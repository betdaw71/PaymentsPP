from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("merchant", "0001_initial"),
        ("payments", "0010_protocol_pay_in_session"),
    ]

    operations = [
        migrations.CreateModel(
            name="PayInTraceLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("merchant_order_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("direction", models.CharField(db_index=True, max_length=32)),
                ("http_method", models.CharField(blank=True, default="", max_length=16)),
                ("url", models.CharField(blank=True, default="", max_length=512)),
                ("status_code", models.IntegerField(blank=True, null=True)),
                ("body", models.JSONField(blank=True, default=dict)),
                ("note", models.CharField(blank=True, default="", max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "merchant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="merchant.merchant",
                    ),
                ),
                (
                    "pay_in",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trace_logs",
                        to="payments.payin",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(fields=["direction", "created_at"], name="payments_pa_directi_6e0f0d_idx"),
                    models.Index(fields=["merchant_order_id", "created_at"], name="payments_pa_merchan_8c8f2a_idx"),
                ],
            },
        ),
    ]
