from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0001_initial"),
        ("merchant", "0005_merchantsolution_max_limit_in_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="merchant",
            name="balance_kzt",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="available_merchant_kzt",
                to="basics.balance",
            ),
        ),
        migrations.AddField(
            model_name="merchant",
            name="frozen_balance_kzt",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="frozen_merchant_kzt",
                to="basics.balance",
            ),
        ),
    ]
