from rest_framework import serializers
from merchant.models import Merchant, MerchantSolution
from rest_framework.validators import UniqueValidator
from basics.models import Trader, TrafficType, PaymentSystem, Balance
from usermanagement.models import SupportMember
from django.contrib.auth.models import User


class PaymentSystemMerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentSystem
        fields = ['id', 'name']


class MerchantShortSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        fields = ('id', 'username',)

    def get_username(self, obj):
        return obj.user.username


class MerchantSerializer(serializers.ModelSerializer):
    payment_systems = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=PaymentSystem.objects.all(),
    )
    email = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        fields = ('id', 'balance', 'payment_systems', 'language', 'telegram', 'email', 'username', 'phone')

    def get_email(self, obj):
        return obj.user.email

    def get_username(self, obj):
        return obj.user.username


class MerchantUpdSerializer(serializers.ModelSerializer):
    payment_systems = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=PaymentSystem.objects.all(),
        required=False
    )
    email = serializers.SerializerMethodField(required=False)
    username = serializers.SerializerMethodField(required=False)

    class Meta:
        model = Merchant
        fields = ('id', 'balance', 'payment_systems', 'language', 'telegram', 'email', 'username', 'phone')

    def get_email(self, obj):
        return obj.user.email

    def get_username(self, obj):
        return obj.user.username


class MerchantCreateSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), validators=[UniqueValidator(queryset=SupportMember.objects.all()), UniqueValidator(queryset=Trader.objects.all()), UniqueValidator(queryset=Merchant.objects.all())])
    telegram = serializers.CharField()
    phone = serializers.CharField()

    class Meta:
        model = Merchant
        fields = ('user', 'telegram', 'phone')

    def create(self, validated_data):
        balance = Balance.objects.create(type=0)
        frozen_balance = Balance.objects.create(type=1)
        trader = Merchant.objects.create(
            user=validated_data['user'],
            telegram=validated_data['telegram'],
            phone=validated_data['phone'],
            balance=balance,
            frozen_balance=frozen_balance,
        )

        return trader


class MerchantSolutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantSolution
        fields = '__all__'