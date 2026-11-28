from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0028_paymentdetails_qr_payload"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentdetails",
            name="bank_name",
            field=models.CharField(blank=True, default=None, max_length=128, null=True),
        ),
    ]
