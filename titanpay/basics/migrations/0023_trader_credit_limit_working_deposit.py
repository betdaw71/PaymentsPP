from decimal import Decimal

from django.db import migrations, models


def seed_psp_credit(apps, schema_editor):
    Trader = apps.get_model("basics", "Trader")
    User = apps.get_model("auth", "User")
    psp = {
        "payplat1",
        "gipay1",
        "visionx1",
        "layerone1",
        "patriot1",
        "prochub1",
        "nexus1",
        "plutus1",
        "bitzone1",
        "protocol1",
        "fairpay_agg",
        "expayone1",
        "playments1",
        "astrum_kzt",
        "concored_mmk",
        "syndicate1",
    }
    ids = list(User.objects.filter(username__in=psp).values_list("id", flat=True))
    Trader.objects.filter(user_id__in=ids).update(credit_limit=Decimal("50000.00"))
    payplat_ids = list(User.objects.filter(username="payplat1").values_list("id", flat=True))
    Trader.objects.filter(user_id__in=payplat_ids).update(working_deposit=Decimal("12000.00"))


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0022_teamlead_frozen_balance"),
    ]

    operations = [
        migrations.AddField(
            model_name="trader",
            name="credit_limit",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="How far below 0 this trader USDT may go. PSP default 50000. Routing uses available + credit_limit.",
                max_digits=32,
            ),
        ),
        migrations.AddField(
            model_name="trader",
            name="working_deposit",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Prepaid float from the provider (PayPlat 12000). Informational; does not stop inflow.",
                max_digits=32,
            ),
        ),
        migrations.RunPython(seed_psp_credit, migrations.RunPython.noop),
    ]
