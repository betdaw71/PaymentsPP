from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("trade", "0005_inorder_agent_fee_outorder_agent_fee"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE trade_inorder ALTER COLUMN agent_fee SET DEFAULT 0;"
                "UPDATE trade_inorder SET agent_fee = 0 WHERE agent_fee IS NULL;"
                "ALTER TABLE trade_outorder ALTER COLUMN agent_fee SET DEFAULT 0;"
                "UPDATE trade_outorder SET agent_fee = 0 WHERE agent_fee IS NULL;"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
