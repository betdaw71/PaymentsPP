from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0020_alter_paymentdetailsgroup_auto_live"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentdetailsgroup",
            name="min_amount_in",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                max_digits=32,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name="paymentdetailsgroup",
            name="max_amount_in",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("999999999"),
                max_digits=32,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
