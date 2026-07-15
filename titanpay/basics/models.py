import time
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from titanpay.settings import RATE_UPD_TIME
from basics.utils import get_bybit_rate
from basics.validators import *
import uuid
from django.db.models import Sum, UniqueConstraint, Q
from django.contrib.auth.models import User
from rest_framework.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver
import datetime
from django.utils import timezone
from decimal import Decimal


class Language(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=32, default="English", unique=True)


class Currency(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=64, unique=True)
    symbol = models.CharField(max_length=6, unique=True)


class PaymentSystem(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=64)
    currency = models.ForeignKey(to=Currency, null=True, on_delete=models.SET_NULL)
    expired_time_in = models.DurationField(default=datetime.timedelta(minutes=10))
    arbitrage_time_in = models.DurationField(default=datetime.timedelta(minutes=30))
    auto_close_amount = models.DecimalField(default=Decimal(-1), decimal_places=2, max_digits=32)
    expired_time_out = models.DurationField(default=datetime.timedelta(minutes=10))
    confirm_time_out = models.DurationField(default=datetime.timedelta(minutes=10))
    constrain_time_out = models.DurationField(default=datetime.timedelta(hours=4))
    required_fields = models.JSONField()  # a dict in the format of {field_name: {"regex": regular_expression_for_field_validation, "pattern": pattern_description}, ...}
    usdt_exchange_rate = models.DecimalField(default=Decimal(1), validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)  # How much currency units for 1 usd
    last_update = models.IntegerField(default=0)
    in_on = models.BooleanField(default=True)  # TODO: check validity of this fields
    out_on = models.BooleanField(default=True)
    sbp_compatible = models.BooleanField(default=True)

    def get_rate(self):
        return self.usdt_exchange_rate

    def update_rate(self, rate):
        import time

        self.usdt_exchange_rate = rate
        self.last_update = int(time.time())
        self.save(update_fields=["usdt_exchange_rate", "last_update"])

    def __str__(self):
        return self.name


class Balance(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    type = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(3)])  # 0 - balance, 1 - frozen balance, 2 - aggregator's balance, 3 - not real balance for usdt deposit txs
    amount = models.DecimalField(default=0, max_digits=32, decimal_places=2)


class TeamLead(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    user = models.OneToOneField(to=User, on_delete=models.CASCADE)
    balance = models.ForeignKey(to=Balance, on_delete=models.DO_NOTHING, null=True, related_name="teamlead")
    language = models.ForeignKey(to=Language, on_delete=models.SET_NULL, null=True)
    telegram = models.CharField(max_length=64, default=None, null=True)
    phone = models.CharField(max_length=64, default=None, null=True)


class TraderTeam(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=64)
    rate_in = models.DecimalField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], max_digits=5, decimal_places=2)
    rate_out = models.DecimalField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], max_digits=5, decimal_places=2)
    teamlead = models.ForeignKey(to=TeamLead, on_delete=models.SET_NULL, null=True, blank=True, default=None)
    teamlead_percentage = models.DecimalField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], max_digits=32, decimal_places=2)
    insurance_deposit = models.DecimalField(default=0, max_digits=32, decimal_places=2)

    def set_rates(self, rate_in, rate_out):
        self.rate_in = rate_in
        self.rate_out = rate_out
        self.save()


class TraderTeamRates(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    team = models.ForeignKey(to=TraderTeam, on_delete=models.CASCADE)
    payment_system = models.ForeignKey(to=PaymentSystem, on_delete=models.CASCADE)
    mdr_in = models.DecimalField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], max_digits=5,
                                  decimal_places=2)
    mdr_out = models.DecimalField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], max_digits=5,
                                   decimal_places=2)


class Trader(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    user = models.OneToOneField(to=User, on_delete=models.CASCADE)
    language = models.ForeignKey(to=Language, on_delete=models.SET_DEFAULT, default=None, null=True)
    telegram = models.CharField(max_length=64, default=None, null=True)
    phone = models.CharField(max_length=64, default=None, null=True)
    boss = models.ForeignKey(to='self', on_delete=models.SET_NULL, null=True)
    is_boss = models.BooleanField(default=False)
    team = models.ForeignKey(to=TraderTeam, on_delete=models.SET_NULL, null=True)
    balance_usdt = models.ForeignKey(to=Balance, on_delete=models.SET_NULL, null=True, related_name='available')
    frozen_balance_usdt = models.ForeignKey(to=Balance, on_delete=models.SET_NULL, null=True, related_name='trader_frozen')
    currency = models.ForeignKey(to=Currency, on_delete=models.SET_NULL, null=True)
    blocked = models.BooleanField(default=False) # TODO: use it
    super_blocked = models.BooleanField(default=False)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)


class TrafficType(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=64, unique=True)
    risk_level = models.IntegerField(default=0)  # the lower, the better quality

    def __str__(self):
        return self.name


def five_minutes_ago():
    return timezone.now() - datetime.timedelta(minutes=5)

class PaymentDetailsGroup(models.Model):
    WORK_TYPE_CHOICES = (
        ('by_card', 'Card'),
        ('by_cash', 'Cash'),
        ('by_deposit_number', 'Deposit Number'),
    )
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    status = models.IntegerField(default=7, validators=[MinValueValidator(0), MaxValueValidator(7)])  # определиться со статусами (0 - inactive, 1 - active, 2 - archived, 3 - blocked by support, 4 - arbitrage blocked, 5 - automatically disabled, 6 - blocked, 7 - setup)

    owner = models.CharField(default="", max_length=255)  # ФИО дропа
    trader = models.ForeignKey(to=Trader, on_delete=models.SET_NULL, null=True)
    currency = models.ForeignKey(to=Currency, on_delete=models.SET_NULL, null=True)
    payment_system = models.ForeignKey(to=PaymentSystem, on_delete=models.SET_NULL, null=True)

    min_amount_out = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    max_amount_out = models.DecimalField(default=1000000, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    amount = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)  # balance
    bic = models.CharField(max_length=9, blank=True, null=True, validators=[bic_validator])
    deposit_number_on = models.BooleanField(default=False)

    in_active = models.BooleanField(default=True)
    out_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=True)

    allowed_traffic = models.ManyToManyField(to=TrafficType)

    limit_per_period = models.DecimalField(default=Decimal(300000), validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    current_volume = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)  # used in current period

    total_volume = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)

    current_out_volume = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)

    auto_live = models.DateTimeField(default=five_minutes_ago, editable=True)

    work_type = models.CharField(max_length=24, default='by_card', choices=WORK_TYPE_CHOICES, null=True, blank=True)

    def update_balance(self):
        self.amount = PaymentDetails.objects.filter(group=self, status=1).aggregate(Sum('amount'))['amount__sum']
        self.save()

    def update_current_volume(self):
        self.current_volume = 0
        self.updated_at = timezone.now()
        self.save()

    def check_liveness(self):
        if int(timezone.now().timestamp()) - int(self.auto_live.timestamp()) > 120 and self.status == 1:
            self.status = 5
            self.save()

        elif int(timezone.now().timestamp()) - int(self.auto_live.timestamp()) < 120 and self.status == 7:
            self.status = 0
            self.save()


class PaymentDetails(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    status = models.IntegerField(default=1, validators=[MinValueValidator(0), MaxValueValidator(2)])  # определиться со статусами 0 - inactive, 1 - active, 2 - archived

    amount = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)

    creation_date = models.DateTimeField(default=timezone.now, editable=False)

    group = models.ForeignKey(to=PaymentDetailsGroup, on_delete=models.CASCADE, related_name='detail')

    sberpay_enabled = models.BooleanField(default=False)
    sbp_enabled = models.BooleanField(default=False)
    card_number = models.CharField(max_length=16, validators=[card_validator], blank=True, null=True)
    phone = models.CharField(max_length=12, validators=[ru_phone_validator], blank=True, null=True)
    deposit_number = models.CharField(max_length=20, validators=[sber_deposit_number_validator])

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=['deposit_number'],
                condition=Q(status=1),
                name='unique_active_deposit_number_per_group'
            ),
            UniqueConstraint(
                fields=['phone'],
                condition=Q(status=1),
                name='unique_active_phone'
            ),
            UniqueConstraint(
                fields=['card_number'],
                condition=Q(status=1),
                name='unique_active_card_number'
            )
        ]

    def save(self, *args, **kwargs):
        if self.sbp_enabled or self.sberpay_enabled:
            self.card_number = None
        super().save(*args, **kwargs)

    def update_balance(self, new_amount):
        self.amount = new_amount
        self.save()
        self.group.update_balance()



