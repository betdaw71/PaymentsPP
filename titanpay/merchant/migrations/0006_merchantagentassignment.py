# Generated manually for merchant agent assignments

import django.core.validators
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('basics', '0006_paymentdetailsgroup_updated_at_and_more'),
        ('merchant', '0005_merchantsolution_max_limit_in_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='MerchantAgentAssignment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ('turnover_percent_in', models.DecimalField(decimal_places=2, default=0, max_digits=5, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ('turnover_percent_out', models.DecimalField(decimal_places=2, default=0, max_digits=5, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('agent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='merchant_assignments', to='basics.teamlead')),
                ('merchant', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='agent_assignment', to='merchant.merchant')),
            ],
        ),
        migrations.AddIndex(
            model_name='merchantagentassignment',
            index=models.Index(fields=['agent', 'is_active'], name='merchant_me_agent_i_6f0a2a_idx'),
        ),
    ]
