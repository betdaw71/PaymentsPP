import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0020_alter_paymentdetailsgroup_auto_live"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentdetailsgroup",
            name="bic",
            field=models.CharField(
                blank=True,
                max_length=11,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        code="invalid_bic",
                        message="Enter a valid BIC (9 digits) or IFSC (11 chars)",
                        regex="^(\\d{9}|[A-Z]{4}0[A-Z0-9]{6})$",
                    )
                ],
            ),
        ),
        migrations.AlterField(
            model_name="paymentdetails",
            name="deposit_number",
            field=models.CharField(
                max_length=20,
                validators=[
                    django.core.validators.RegexValidator(
                        code="invalid_deposit_number",
                        message="Enter a valid account number (9-20 digits)",
                        regex="^\\d{9,20}$",
                    )
                ],
            ),
        ),
    ]
