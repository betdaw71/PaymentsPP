from django.db import models
from django.db import models
import uuid
from basics.models import PaymentDetailsGroup
from django.utils import timezone
from django.contrib.auth.models import User


class TGBot(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    user = models.ForeignKey(to=User, on_delete=models.CASCADE, null=True, related_name='tgbot')
