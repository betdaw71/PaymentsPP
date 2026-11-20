from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trade", "0008_watched_deposit_wallet"),
    ]

    operations = [
        migrations.AlterField(
            model_name="inorder",
            name="pic",
            field=models.URLField(max_length=500),
        ),
    ]
