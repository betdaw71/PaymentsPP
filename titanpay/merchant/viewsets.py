from decimal import Decimal, InvalidOperation

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.decorators import action

from basics.models import PaymentSystem
from merchant.serializers import MerchantSerializer, MerchantCreateSerializer, MerchantSolutionSerializer, \
    MerchantUpdSerializer, MerchantShortSerializer
from merchant.models import Merchant, MerchantSolution
from rest_framework import viewsets, status
from rest_framework.permissions import IsAdminUser
from basics.permissions import HeadSupportPermission, DebugPermission, MerchantPermission
from rest_framework.response import Response
from django.db import transaction


class MerchantViewSet(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = Merchant.objects.all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get', 'post', 'patch']
    NON_PROTECTED_FIELDS = ('phone', 'telegram')

    def get_permissions(self):
        if self.action == 'partial_update':
            return [MerchantPermission()]
        return [HeadSupportPermission()]

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return MerchantUpdSerializer
        elif self.action == 'create':
            return MerchantCreateSerializer
        elif self.action == 'list':
            return MerchantShortSerializer
        else:
            return MerchantSerializer

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.user != request.user:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not merchant!'})

        for field in request.data.keys():
            if field not in self.NON_PROTECTED_FIELDS:
                return Response({field: f"{field} cannot be changed"},
                                status=status.HTTP_400_BAD_REQUEST)

        return super(MerchantViewSet, self).update(request, *args, **kwargs)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = MerchantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['patch'], url_path='rolling-reserve')
    def set_rolling_reserve(self, request, id=None):
        merchant = self.get_object()
        raw = request.data.get('rolling_reserve')
        if raw is None:
            return Response({'error': 'rolling_reserve is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            return Response({'error': 'rolling_reserve must be a number'}, status=status.HTTP_400_BAD_REQUEST)
        if value < 0:
            return Response({'error': 'rolling_reserve cannot be negative'}, status=status.HTTP_400_BAD_REQUEST)
        merchant.rolling_reserve = value
        merchant.save(update_fields=['rolling_reserve'])
        return Response({'id': str(merchant.id), 'rolling_reserve': str(merchant.rolling_reserve)})


class MerchantSolutionViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    queryset = Merchant.objects.all()
    serializer_class = MerchantSolutionSerializer
    permission_classes = [HeadSupportPermission | DebugPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'supportmember'):
            if user.supportmember.is_head:
                return MerchantSolution.objects.all()
        elif hasattr(user, 'merchant'):
            return MerchantSolution.objects.filter(merchant=user.merchant)
        else:
            return MerchantSolution.objects.none()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = MerchantSolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        instance.status = 2
        instance.save()

        return Response(status=status.HTTP_204_NO_CONTENT)
