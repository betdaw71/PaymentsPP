from django.db.models import Sum
from django.utils import timezone
from uuid import UUID
from basics.models import Language, Trader
from usermanagement.models import SupportMember
from merchant.models import Merchant
from usermanagement.serializers import MyTokenObtainPairSerializer, RegisterMerchantSerializer, \
    RegisterTraderSerializer, TraderChangeSerializer
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth.models import User
from usermanagement.serializers import RegisterSerializer, ChangePasswordSerializer, RegisterSupportSerializer
from rest_framework.decorators import api_view, permission_classes
import jwt
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import update_session_auth_hash
from rest_framework import generics, status
from rest_framework.response import Response
from basics.permissions import HeadSupportPermission, TraderPermission
from titanpay.settings import LOW_DEPOSIT_LEVEL
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.decorators import otp_required
import qrcode
from io import BytesIO
from base64 import b64encode
from trade.models import InOrder, OutOrder, WithdrawalRequest


@api_view(['POST'])
@permission_classes([IsAdminUser])
def super_block(request, *args, **kwargs):
    traders = Trader.objects.all()
    for trader in traders:
        trader.super_blocked = True
        trader.save()

    return Response(status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def super_unblock(request, *args, **kwargs):
    traders = Trader.objects.all()
    for trader in traders:
        trader.super_blocked = False
        trader.save()

    return Response(status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([HeadSupportPermission])
def update_user(request, id):
    user_id = id
    if not Trader.objects.filter(id=user_id).exists():
        return Response(status=status.HTTP_404_NOT_FOUND)
    trader = Trader.objects.get(id=user_id)

    serializer = TraderChangeSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)
    validated_data = serializer.validated_data

    email = validated_data.get('email')

    if email is not None:
        try:
            trader.user.email = email
            trader.user.save()
        except:
            pass

    phone = validated_data.get('phone')

    if phone is not None:
        try:
            trader.phone = phone
            trader.save()
        except:
            pass

    telegram = validated_data.get('telegram')

    if telegram is not None:
        try:
            trader.telegram = telegram
            trader.save()
        except:
            pass

    username = validated_data.get('username')

    if telegram is not None:
        try:
            trader.user.username = username
            trader.user.save()
        except:
            pass

    return Response(status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_me(request, *args, **kwargs):

    user = request.user

    data = {
        "username": user.username,
        "first_name": user.first_name,
        # "last_name": user.last_name,
        "email": user.email,
    }

    if hasattr(user, 'trader'):
        if user.trader.super_blocked:
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

        data["language"] = user.trader.language.name
        data["telegram"] = user.trader.telegram
        data["phone"] = user.trader.phone
        data["currency"] = user.trader.currency.symbol
        data["role"] = 1 if not user.trader.is_boss else 2
        data["deposit"] = user.trader.balance_usdt.amount > LOW_DEPOSIT_LEVEL
        data["object_id"] = user.trader.id
        data["current_balance"] = float(user.trader.balance_usdt.amount)
        data["hold"] = float(user.trader.frozen_balance_usdt.amount)

        start_of_today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        today_inorders = InOrder.objects.filter(creation_date__gte=start_of_today, status__name="Completed", payment_details__group__trader=user.trader)
        today_outorders = OutOrder.objects.filter(creation_date__gte=start_of_today, status__name="Completed", payment_details__group__trader=user.trader)

        total_sum_in = today_inorders.aggregate(total=Sum('trader_fee'))['total']
        total_sum_out = today_outorders.aggregate(total=Sum('trader_fee'))['total']

        sum_value = float(total_sum_in or 0) + float(total_sum_out or 0)

        data["income"] = sum_value

    elif hasattr(user, 'supportmember'):
        data["language"] = user.supportmember.language.name
        data["telegram"] = user.supportmember.telegram
        data["phone"] = user.supportmember.phone
        data["role"] = 4 if not user.supportmember.is_head else 5
        data["deposit"] = True
        data["object_id"] = user.supportmember.id

    elif hasattr(user, 'merchant'):
        data["language"] = user.merchant.language.name
        data["telegram"] = user.merchant.telegram
        data["phone"] = user.merchant.phone
        data["role"] = 3
        data["current_balance"] = float(user.merchant.balance.amount)
        data["hold"] = float(user.merchant.frozen_balance.amount)
        data["deposit"] = True
        data["object_id"] = user.merchant.id
        data["payment_systems"] = [payment_system.name for payment_system in user.merchant.payment_systems.all()]

    elif hasattr(user, 'submerchant'):
        data["language"] = user.submerchant.language.name
        data["telegram"] = user.submerchant.telegram
        data["phone"] = user.submerchant.phone
        data["role"] = 6
        data["current_balance"] = float(user.submerchant.merchant.balance.amount)
        data["hold"] = float(user.submerchant.merchant.frozen_balance.amount)
        data["deposit"] = True
        data["object_id"] = user.submerchant.id
        data["payment_systems"] = []

    elif hasattr(user, 'teamlead'):
        data["language"] = user.teamlead.language.name
        data["telegram"] = user.teamlead.telegram
        data["phone"] = user.teamlead.phone
        data["role"] = 7
        data["current_balance"] = float(user.teamlead.balance.amount)
        data["deposit"] = True
        data["object_id"] = user.teamlead.id
        data["payment_systems"] = []
        from merchant.models import MerchantAgentAssignment
        data["has_merchant_agent"] = MerchantAgentAssignment.objects.filter(
            agent=user.teamlead, is_active=True
        ).exists()

    data["user_id"] = user.id

    return Response(data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_notifications(request, *args, **kwargs):

    user = request.user

    active = False
    content = []

    if hasattr(user, 'trader'):

        if user.trader.super_blocked:
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)
        trader = user.trader

        arbitrage_count = InOrder.objects.filter(payment_details__group__trader=trader, status__name="Arbitrage").count()
        if arbitrage_count != 0:
            active = True
            content.append({"message": f"Открытых арбитражей: {arbitrage_count}"})

    elif hasattr(user, 'supportmember'):
        supportmember = user.supportmember
        if user.supportmember.is_head:
            withdrawal_count = WithdrawalRequest.objects.filter(status=0).count()
            if withdrawal_count != 0:
                active = True
                content.append({"message": f"Заявок на вывод: {withdrawal_count}"})
        manual_check_count = OutOrder.objects.filter(payment_details__group__trader__team__in=supportmember.controlled_teams.all(), status__name="Manual check").count()
        if manual_check_count != 0:
            active = True
            content.append({"message": f"Непроверенных out-ордеров: {manual_check_count}"})

    data = {
        "active": active,
        "content": content
    }

    return Response(status=status.HTTP_200_OK, data=data)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (HeadSupportPermission,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class RegisterSupportView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (HeadSupportPermission,)
    serializer_class = RegisterSupportSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class RegisterMerchantView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (HeadSupportPermission,)
    serializer_class = RegisterMerchantSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class RegisterTraderView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (HeadSupportPermission,)
    serializer_class = RegisterTraderSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class MyObtainTokenPairView(TokenObtainPairView):
    permission_classes = (AllowAny,)
    serializer_class = MyTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        stay_signed = False

        if "stay_signed" in request.data and request.data["stay_signed"]:
            stay_signed = True

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])

        data = serializer.validated_data

        token = request.data.get('code')

        user = User.objects.get(username=request.data.get('username').replace(' ', ''))

        device = TOTPDevice.objects.filter(user=user, name='default')

        if device.exists():

            if not device.first().verify_token(token):
                return Response({"detail": "Invalid 2FA code"}, status=status.HTTP_403_FORBIDDEN)

        data.update({"stay_signed": stay_signed})

        decoded = jwt.decode(str(data["access"]), algorithms=["HS256"], options={"verify_signature": False})
        data.update({"username": decoded['username'], "role": decoded['role']})

        return Response(data, status=status.HTTP_200_OK)


class ChangePasswordView(generics.CreateAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = (IsAuthenticated,)

    def create(self, request, *args, **kwargs):
        user = request.user
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Check old password
            if not user.check_password(serializer.data.get('old_password')):
                return Response({'old_password': ['Wrong password.']}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(serializer.data.get('password'))
            user.save()
            update_session_auth_hash(request, user)
            return Response({'status': 'Password changed successfully'}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TwoFactorSetupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        device, created = TOTPDevice.objects.get_or_create(user=user, name='default')
        if created:
            device.generate_challenge()
        qr_code = qrcode.make(device.config_url)
        stream = BytesIO()
        qr_code.save(stream, format="PNG")
        qr_code_b64 = b64encode(stream.getvalue()).decode()
        return Response({'qr_code': qr_code_b64})
