from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from basics.models import PaymentSystem
from merchant.serializers import MerchantSerializer, MerchantCreateSerializer, MerchantSolutionSerializer, \
    MerchantUpdSerializer, MerchantShortSerializer, MerchantAgentAssignmentSerializer
from merchant.models import Merchant, MerchantSolution, MerchantAgentAssignment
from rest_framework import viewsets, status
from rest_framework.permissions import IsAdminUser
from basics.permissions import HeadSupportPermission, DebugPermission, MerchantPermission, TeamLeadPermission
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


class MerchantAgentAssignmentViewSet(viewsets.ModelViewSet):
    lookup_field = 'id'
    serializer_class = MerchantAgentAssignmentSerializer
    permission_classes = [HeadSupportPermission | TeamLeadPermission | DebugPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['merchant', 'agent', 'is_active']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_queryset(self):
        user = self.request.user
        qs = MerchantAgentAssignment.objects.select_related('merchant__user', 'agent__user')
        if hasattr(user, 'teamlead') and not user.is_superuser and not (
            hasattr(user, 'supportmember') and user.supportmember.is_head
        ):
            return qs.filter(agent=user.teamlead)
        return qs.all()

    def _forbid_teamlead_write(self, request):
        if hasattr(request.user, 'teamlead') and not request.user.is_superuser and not (
            hasattr(request.user, 'supportmember') and request.user.supportmember.is_head
        ):
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'Forbidden'})
        return None

    def create(self, request, *args, **kwargs):
        denied = self._forbid_teamlead_write(request)
        if denied is not None:
            return denied
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        denied = self._forbid_teamlead_write(request)
        if denied is not None:
            return denied
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        denied = self._forbid_teamlead_write(request)
        if denied is not None:
            return denied
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        denied = self._forbid_teamlead_write(request)
        if denied is not None:
            return denied
        return super().destroy(request, *args, **kwargs)
