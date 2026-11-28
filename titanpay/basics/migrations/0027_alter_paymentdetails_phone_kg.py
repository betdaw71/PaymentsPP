from django.db import migrations, models

import basics.validators


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0026_trader_manual_mode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentdetails",
            name="phone",
            field=models.CharField(
                blank=True,
                max_length=16,
                null=True,
                validators=[basics.validators.ru_phone_validator],
            ),
        ),
    ]
