from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("basics", "0026_trader_manual_mode"),
        ("trade", "0007_inorder_dual_fx"),
    ]

    operations = [
        migrations.CreateModel(
            name="WatchedDepositWallet",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("address_public", models.CharField(max_length=64, unique=True)),
                ("enabled", models.BooleanField(default=True)),
                ("watch_from", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_polled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                (
                    "trader",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="watched_deposit_wallets",
                        to="basics.trader",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CryptoDepositCredit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("tx_id", models.CharField(max_length=128, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=32)),
                ("from_address", models.CharField(blank=True, default="", max_length=128)),
                ("block_at", models.DateTimeField(blank=True, null=True)),
                ("credited", models.BooleanField(default=False)),
                ("note", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="credits",
                        to="trade.watcheddepositwallet",
                    ),
                ),
            ],
        ),
    ]
