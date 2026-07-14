import uuid
from django.contrib.auth.models import User
from django.db import models
from merchant.models import Merchant
from basics.models import Language, TraderTeam


class SupportMember(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    language = models.ForeignKey(to=Language, on_delete=models.SET_NULL, null=True)
    telegram = models.CharField(max_length=64, default=None, null=True)
    phone = models.CharField(max_length=64, default=None, null=True)
    user = models.OneToOneField(to=User, on_delete=models.CASCADE)
    controlled_teams = models.ManyToManyField(to=TraderTeam)
    controlled_merchants = models.ManyToManyField(to=Merchant)
    is_head = models.BooleanField(default=False)

