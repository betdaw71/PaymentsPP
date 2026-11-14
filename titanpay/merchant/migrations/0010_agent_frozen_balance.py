import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0024_platform_expense"),
        ("merchant", "0009_agent_and_merchant_agent"),
    ]

    operations = [
        migrations.AddField(
            model_name="agent",
            name="frozen_balance",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="frozen_agent",
                to="basics.balance",
            ),
        ),
    ]
