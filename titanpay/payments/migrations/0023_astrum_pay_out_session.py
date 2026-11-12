from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0022_payplat_pay_in_session"),
    ]

    operations = [
        migrations.CreateModel(
            name="AstrumPayOutSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("external_id", models.CharField(db_index=True, max_length=128)),
                ("provider_application_id", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("create_response", models.JSONField(blank=True, default=dict)),
                ("last_webhook_payload", models.JSONField(blank=True, default=dict)),
                ("last_notified_status", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "pay_out",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="astrum_session",
                        to="payments.payout",
                    ),
                ),
            ],
        ),
    ]
