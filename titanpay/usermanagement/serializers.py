from rest_framework import serializers
from django.contrib.auth.models import User
from rest_framework.validators import UniqueValidator
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
import time
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate

from basics.utils import generate_address
from sms.models import TraderDevice
from rest_framework.authtoken.models import Token
from basics.models import TrafficType, TraderTeam, Language, PaymentSystem, Trader, Currency, Balance
from usermanagement.models import SupportMember
from merchant.models import Merchant
from trade.models import Address


class TraderChangeSerializer(serializers.Serializer):
    email = serializers.CharField(required=False, write_only=True)
    phone = serializers.CharField(required=False, write_only=True)
    username = serializers.CharField(required=False, write_only=True)
    telegram = serializers.CharField(required=False, write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    password = serializers.CharField(required=True)
    password2 = serializers.CharField(required=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not authenticate(username=user.username, password=value):
            raise serializers.ValidationError('Old password is not correct')
        return value

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password2': 'Passwords must match.'})
        return data


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    stay_signed = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        data = super(CustomTokenObtainPairSerializer, self).validate(attrs)
        return data


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    stay_signed_in = serializers.BooleanField(default=False)
    code = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    default_error_messages = {
        "no_active_account": ("The password is wrong or the user doesn't exist")
    }

    @classmethod
    def get_token(cls, user):
        token = super(MyTokenObtainPairSerializer, cls).get_token(user)
        token['username'] = user.username

        if hasattr(user, 'trader'):
            token['role'] = 1
            if user.trader.is_boss:
                token['role'] = 2
        elif hasattr(user, 'merchant'):
            token['role'] = 3
        elif hasattr(user, 'supportmember'):
            token['role'] = 4
            if user.supportmember.is_head:
                token['role'] = 5
        elif hasattr(user, 'submerchant'):
            token['role'] = 6
        elif hasattr(user, 'teamlead'):
            token['role'] = 7
        return token


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all())]
    )

    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    access = serializers.SerializerMethodField(read_only=True)
    refresh = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'password2', 'email', "access", "refresh")

    def get_refresh(self, obj):
        token = MyTokenObtainPairSerializer.get_token(obj)
        return str(token)

    def get_access(self, obj):
        token = MyTokenObtainPairSerializer.get_token(obj)
        access_token = token.access_token
        return str(access_token)

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})

        return attrs

    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data['username'],
            email=validated_data['email'],
        )

        user.set_password(validated_data['password'])
        user.save()
        return user


class RegisterSupportSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all())]
    )

    first_name = serializers.CharField(write_only=True, required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    controlled_teams = serializers.PrimaryKeyRelatedField(queryset=TraderTeam.objects.all(), many=True, write_only=True)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'password', 'password2', 'email', 'controlled_teams')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})

        return attrs

    def create(self, validated_data):
        controlled_teams = validated_data.pop('controlled_teams')
        language = Language.objects.get(name="English")

        user = User.objects.create(
            first_name=validated_data['first_name'],
            username=validated_data['username'],
            email=validated_data['email'],
        )

        user.set_password(validated_data['password'])
        user.save()

        support_member = SupportMember.objects.create(user=user, language=language)

        for team in controlled_teams:
            support_member.controlled_teams.add(team)

        support_member.save()

        return user


class RegisterMerchantSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all())]
    )

    first_name = serializers.CharField(write_only=True, required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    address = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'password', 'password2', 'email', 'address')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})

        return attrs

    def create(self, validated_data):
        user = User.objects.create(
            first_name=validated_data['first_name'],
            username=validated_data['username'],
            email=validated_data['email'],
        )
        user.set_password(validated_data['password'])
        user.save()
        language = Language.objects.get(name="English")
        balance = Balance.objects.create(type=0)
        frozen_balance = Balance.objects.create(type=1)
        merchant = Merchant.objects.create(user=user, language=language, balance=balance, frozen_balance=frozen_balance)

        Address.objects.create(balance=merchant.balance, address_public=generate_address())
        return user


class RegisterTraderSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all())]
    )

    first_name = serializers.CharField(write_only=True, required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    team = serializers.PrimaryKeyRelatedField(queryset=TraderTeam.objects.all(), write_only=True)
    boss = serializers.PrimaryKeyRelatedField(queryset=Trader.objects.all(), allow_null=True, required=False, write_only=True)
    currency = serializers.PrimaryKeyRelatedField(queryset=Currency.objects.all(), write_only=True)
    address = serializers.CharField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'password', 'password2', 'email', 'team', 'boss', 'currency', 'address')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})

        if attrs.get('boss', None) is None and attrs.get('address', None) is None:
            raise serializers.ValidationError({"address": "Should not be null if you create a boss."})
        return attrs

    def create(self, validated_data):
        currency = validated_data.pop('currency')
        team = validated_data.pop('team')
        language = Language.objects.get(name="Russian")
        boss = validated_data.pop('boss', None)

        user = User.objects.create(
            first_name=validated_data['first_name'],
            username=validated_data['username'],
            email=validated_data['email'],
        )

        sms_user = User.objects.create(
            first_name=validated_data['first_name'],
            username='sms'+validated_data['username'],
            email='sms'+validated_data['email'],
        )

        user.set_password(validated_data['password'])
        sms_user.set_password(validated_data['password']+'sms')
        user.save()
        sms_user.save()

        balance = Balance.objects.create(type=0)
        frozen_balance = Balance.objects.create(type=1)

        is_boss = boss is None

        if not is_boss:
            trader = Trader.objects.create(user=user, language=boss.language, currency=boss.currency, team=boss.team, boss=boss, is_boss=is_boss, balance_usdt=balance, frozen_balance_usdt=frozen_balance)
        else:
            trader = Trader.objects.create(user=user, language=language, currency=currency, team=team, boss=boss, is_boss=is_boss, balance_usdt=balance, frozen_balance_usdt=frozen_balance)
            Address.objects.create(balance=trader.balance_usdt, address_public=generate_address())

        TraderDevice.objects.create(user=sms_user, trader=trader)
        Token.objects.create(user=sms_user)
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ('id', 'username')
