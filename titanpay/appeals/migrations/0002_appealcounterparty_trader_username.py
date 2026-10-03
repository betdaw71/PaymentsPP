import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appeals", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="appealcounterparty",
            name="trader_username",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Локальный трейдер (если не PSP), например kzt_c2c_test",
                max_length=64,
            ),
        ),
    ]
