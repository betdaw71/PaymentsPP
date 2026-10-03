from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0021_paymentdetailsgroup_min_max_amount_in"),
    ]

    operations = [
        migrations.AddField(
            model_name="teamlead",
            name="frozen_balance",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="teamlead_frozen",
                to="basics.balance",
            ),
        ),
    ]
