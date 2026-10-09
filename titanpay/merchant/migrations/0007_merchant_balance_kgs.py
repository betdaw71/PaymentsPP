from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0001_initial"),
        ("merchant", "0006_merchant_balance_kzt"),
    ]

    operations = [
        migrations.AddField(
            model_name="merchant",
            name="balance_kgs",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="available_merchant_kgs",
                to="basics.balance",
            ),
        ),
        migrations.AddField(
            model_name="merchant",
            name="frozen_balance_kgs",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="frozen_merchant_kgs",
                to="basics.balance",
            ),
        ),
    ]
