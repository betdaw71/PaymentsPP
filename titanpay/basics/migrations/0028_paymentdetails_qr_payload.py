from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0027_alter_paymentdetails_phone_kg"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentdetails",
            name="qr_payload",
            field=models.TextField(blank=True, default=None, null=True),
        ),
    ]
