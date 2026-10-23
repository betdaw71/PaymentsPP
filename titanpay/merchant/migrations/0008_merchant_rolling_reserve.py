from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("merchant", "0007_merchant_balance_kgs"),
    ]

    operations = [
        migrations.AddField(
            model_name="merchant",
            name="rolling_reserve",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="USDT sent to merchant as rolling reserve. Informational; not part of available balance. "
                          "Net position = rolling_reserve - available_balance.",
                max_digits=20,
            ),
        ),
    ]
