from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appeals", "0002_appealcounterparty_trader_username"),
    ]

    operations = [
        migrations.AddField(
            model_name="payinappeal",
            name="merchant_inline_clicked",
            field=models.BooleanField(
                default=False,
                help_text="Userbot already pressed Mel Transaction Bot confirm/reject on the source message",
            ),
        ),
    ]
