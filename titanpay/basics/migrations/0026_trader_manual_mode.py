from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0025_paymentdetailsgroup_deal_spacing"),
    ]

    operations = [
        migrations.AddField(
            model_name="trader",
            name="manual_mode",
            field=models.BooleanField(default=False),
        ),
        migrations.RemoveField(
            model_name="paymentdetailsgroup",
            name="skip_auto_live",
        ),
    ]
