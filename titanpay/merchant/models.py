from django.db import models
from django.contrib.auth.models import User
from basics.models import Balance, PaymentSystem, TrafficType, Language
import uuid
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import MaxValueValidator, MinValueValidator
from decimal import Decimal


class Merchant(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    user = models.OneToOneField(to=User, on_delete=models.CASCADE)
    balance = models.ForeignKey(to=Balance, on_delete=models.DO_NOTHING, null=True, related_name='available_merchant')
    frozen_balance = models.ForeignKey(to=Balance, on_delete=models.DO_NOTHING, null=True, related_name='frozen_merchant')
    payment_systems = models.ManyToManyField(to=PaymentSystem)
    language = models.ForeignKey(to=Language, on_delete=models.SET_NULL, null=True)
    telegram = models.CharField(max_length=64, default=None, null=True)
    phone = models.CharField(max_length=64, default=None, null=True)


class MerchantSolution(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    status = models.IntegerField(default=1, editable=True, validators=[MinValueValidator(0), MaxValueValidator(2)])
    payment_system = models.ForeignKey(to=PaymentSystem, on_delete=models.CASCADE)
    merchant = models.ForeignKey(to=Merchant, on_delete=models.CASCADE)
    mdr_in = models.DecimalField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], max_digits=32, decimal_places=2)
    mdr_out = models.DecimalField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], max_digits=32, decimal_places=2)
    traffic = models.ForeignKey(to=TrafficType, on_delete=models.CASCADE)
    ftd = models.BooleanField(default=False)
    autoclose_arbitrage = models.BooleanField(default=False)
    min_limit_in = models.DecimalField(default=0, max_digits=32, decimal_places=2)
    min_limit_out = models.DecimalField(default=0, max_digits=32, decimal_places=2)
    max_limit_in = models.DecimalField(default=0, max_digits=32, decimal_places=2)
    max_limit_out = models.DecimalField(default=0, max_digits=32, decimal_places=2)


class SubMerchant(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    user = models.OneToOneField(to=User, on_delete=models.CASCADE)
    language = models.ForeignKey(to=Language, on_delete=models.SET_NULL, null=True)
    telegram = models.CharField(max_length=64, default=None, null=True)
    phone = models.CharField(max_length=64, default=None, null=True)
    merchant = models.ForeignKey(to=Merchant, on_delete=models.CASCADE)









































# copy_merchant.py
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'titanpay.settings')
import django

from django.contrib.auth.models import User
from merchant.models import Merchant, MerchantSolution
from basics.models import PaymentSystem, Currency, TrafficType
from trade.models import Balance
import uuid

def copy_merchant(source_username="Kingsman", target_name="Kingsman2"):
    """Копирует мерчанта со всеми настройками"""
    
    print(f"🎯 Копирование мерчанта: {source_username} → {target_name}")
    
    # 1. Находим исходного мерчанта через пользователя
    try:
        source_user = User.objects.get(username=source_username)
    except User.DoesNotExist:
        print(f"❌ Пользователь {source_username} не найден")
        print("Доступные пользователи-мерчанты:")
        for user in User.objects.filter(groups__name="merchant")[:10]:
            print(f"  - {user.username}")
        return
    
    # Проверяем, что это мерчант
    if not hasattr(source_user, 'merchant'):
        print(f"❌ Пользователь {source_username} не является мерчантом")
        return
    
    source_merchant = source_user.merchant
    print(f"✅ Найден исходный мерчант: {source_user.username}")
    
    # 2. Проверяем, нет ли уже пользователя с таким именем
    target_username = target_name.lower().replace(" ", "_")
    if User.objects.filter(username=target_username).exists():
        print(f"❌ Пользователь с именем {target_username} уже существует")
        return
    
    # 3. Создаем пользователя для нового мерчанта
    user = User.objects.create_user(
        username=target_username,
        email=f"{target_username}@example.com",
        password="temporary_password123"
    )
    
    print(f"✅ Создан пользователь: {target_username}")
    
    # 4. Создаем балансы для нового мерчанта
    balance = Balance.objects.create(
        type=0,  # обычный баланс
        amount=0
    )
    
    frozen_balance = Balance.objects.create(
        type=1,  # замороженный баланс
        amount=0
    )
    
    print(f"✅ Созданы балансы")
    
    # 5. Создаем нового мерчанта с теми же полями
    target_merchant = Merchant.objects.create(
        user=user,
        phone=source_merchant.phone or "",
        telegram=source_merchant.telegram or "",
        language=source_merchant.language,
        balance=balance,
        frozen_balance=frozen_balance,
    )
    
    print(f"✅ Создан новый мерчант")
    print(f"   Пользователь: {target_merchant.user.username}")
    
    # 6. Копируем все решения (MerchantSolution) исходного мерчанта
    source_solutions = MerchantSolution.objects.filter(merchant=source_merchant)
    
    copied_solutions = 0
    
    for source_solution in source_solutions:
        # Создаем новое решение для целевого мерчанта
        target_solution = MerchantSolution.objects.create(
            merchant=target_merchant,
            payment_system=source_solution.payment_system,
            mdr_in=source_solution.mdr_in,
            mdr_out=source_solution.mdr_out
        )
        
        # Копируем типы трафика
        for traffic in source_solution.traffic.all():
            target_solution.traffic.add(traffic)
        
        copied_solutions += 1
        print(f"✅ Скопировано решение: {source_solution.payment_system.name}")
    
    print(f"\n📊 ИТОГО:")
    print(f"   Мерчант создан: {target_merchant.user.username}")
    print(f"   Скопировано решений: {copied_solutions}")
    print(f"   Баланс: ${target_merchant.balance.amount}")
    
    # 7. Показываем все решения нового мерчанта
    print(f"\n💰 НАСТРОЙКИ НОВОГО МЕРЧАНТА:")
    target_solutions = MerchantSolution.objects.filter(merchant=target_merchant)
    
    for solution in target_solutions:
        traffic_names = ", ".join([t.name for t in solution.traffic.all()])
        print(f"   {solution.payment_system.name}: IN={solution.mdr_in}%, OUT={solution.mdr_out}% (Трафик: {traffic_names})")
    
    return target_merchant

# Запуск - используем username, а не name
#copy_merchant("Kingsman", "Kingsman2")
