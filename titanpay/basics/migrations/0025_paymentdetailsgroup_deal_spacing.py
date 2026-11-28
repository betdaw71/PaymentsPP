from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0024_platform_expense"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentdetailsgroup",
            name="amount_diff",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                max_digits=32,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name="paymentdetailsgroup",
            name="deal_interval_sec",
            field=models.IntegerField(
                default=0,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name="paymentdetailsgroup",
            name="skip_auto_live",
            field=models.BooleanField(default=False),
        ),
    ]
