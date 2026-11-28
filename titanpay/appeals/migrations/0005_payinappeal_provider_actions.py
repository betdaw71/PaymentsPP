from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appeals", "0004_payinappeal_provider_nudges"),
    ]

    operations = [
        migrations.AddField(
            model_name="payinappeal",
            name="provider_has_media",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="payinappeal",
            name="provider_original_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="payinappeal",
            name="provider_reject_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="payinappeal",
            name="status",
            field=models.CharField(
                choices=[
                    ("created", "Created"),
                    ("sent_to_provider", "Sent to provider"),
                    ("awaiting_reject_reason", "Awaiting reject reason"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("duplicate", "Duplicate"),
                    ("failed", "Failed"),
                    ("no_provider_chat", "No provider chat"),
                ],
                default="created",
                max_length=32,
            ),
        ),
    ]
