from django.db import models
import uuid
from basics.models import PaymentDetailsGroup
from django.utils import timezone
from basics.models import Trader
from django.contrib.auth.models import User


class SMS(models.Model):
    STATUS_CHOICES = (
        ('success', 'Success'),
        ('pending', 'Pending'),
        ('not-found', 'Not Found'),
        ('red-block', 'Red Block'),
        ('fz-block', 'FZ Block'),
        ('compr-block', 'Compromise Block'),
        ('wrong-state', 'Wrong State'),
    )
    text = models.CharField(max_length=255)
    status = models.CharField(default='pending', max_length=11, choices=STATUS_CHOICES)
    date = models.DateTimeField(default=timezone.now, editable=False)
    device = models.ForeignKey(to=PaymentDetailsGroup, on_delete=models.SET_NULL, null=True, blank=True)


class TraderDevice(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    user = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, related_name='traderdevice')
    trader = models.ForeignKey(to=Trader, on_delete=models.CASCADE, null=True)
