from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appeals", "0003_payinappeal_merchant_inline_clicked"),
    ]

    operations = [
        migrations.AddField(
            model_name="payinappeal",
            name="provider_nudge_1h_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payinappeal",
            name="provider_nudge_3h_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
