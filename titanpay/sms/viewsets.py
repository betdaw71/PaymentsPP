from django_filters.rest_framework import DjangoFilterBackend
import django_filters
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework import viewsets, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from basics.permissions import SupportPermission, TraderPermission, DebugPermission, MerchantPermission
from basics.paginators import StandardResultsSetPagination
from sms.models import SMS
from sms.serializers import SMSSerializer


class SMSFilter(django_filters.FilterSet):
    class Meta:
        model = SMS
        fields = {
            'id': ['exact'],
            'date': ['range'],
            'device': ['exact'],
            'status': ['in'],
            'device__trader__team__name': ['in'],
            'device__trader__user__username': ['in'],
            'device__owner': ['exact'],
            'inorder': ['exact'],
            'outorder': ['exact'],
            'text': ['icontains']

        }


class SMSViewSet(viewsets.ModelViewSet):
    lookup_field = 'id'
    serializer_class = SMSSerializer
    permission_classes = [SupportPermission | TraderPermission | IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SMSFilter
    filterset_fields = ['id', 'date', 'device', 'status']
    search_fields = ['id', 'date', 'device']
    ordering_fields = ['id', 'date', 'device']
    pagination_class = StandardResultsSetPagination
    ordering = ['-date']
    http_method_names = ['get']

    def get_queryset(self):
        user = self.request.user

        if hasattr(user, 'trader'):

            if user.trader.is_boss:
                return SMS.objects.filter(device__trader__team=user.trader.team)
            else:
                return SMS.objects.filter(device__trader=user.trader)

        elif hasattr(user, 'supportmember'):
            return SMS.objects.filter(device__trader__team__in=user.supportmember.controlled_teams.all())

        return SMS.objects.none()
