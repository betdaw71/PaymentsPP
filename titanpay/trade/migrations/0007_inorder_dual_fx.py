from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trade", "0006_agent_fee_db_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="inorder",
            name="merchant_rate",
            field=models.DecimalField(decimal_places=6, default=0, max_digits=32),
        ),
        migrations.AddField(
            model_name="inorder",
            name="psp_rate",
            field=models.DecimalField(decimal_places=6, default=0, max_digits=32),
        ),
        migrations.AddField(
            model_name="inorder",
            name="psp_usd_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=32),
        ),
    ]
