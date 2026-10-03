# Generated manually for agent_fee on orders

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trade', '0004_inorder_rejection_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='inorder',
            name='agent_fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=32, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name='outorder',
            name='agent_fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=32, validators=[django.core.validators.MinValueValidator(0)]),
        ),
    ]
