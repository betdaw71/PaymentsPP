import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0023_trader_credit_limit_working_deposit"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformExpense",
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
                ("amount", models.DecimalField(decimal_places=2, max_digits=32)),
                ("comment", models.CharField(max_length=256)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("source", models.CharField(default="telegram", max_length=64)),
            ],
        ),
    ]
