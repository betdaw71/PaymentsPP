from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from rest_framework.response import Response
from basics.models import Trader, Currency, TraderTeam, Balance, TrafficType, PaymentSystem
from basics.permissions import TraderPermission, DebugPermission, SupportPermission, HeadSupportPermission
from basics.serializers import PaymentSystemSerializer, TrafficTypeSerializer
from merchant.models import MerchantSolution, Merchant
from merchant.serializers import MerchantSolutionSerializer


@api_view(['GET'])
@permission_classes([HeadSupportPermission | DebugPermission])
def get_solutions(request, *args, **kwargs):
    user = request.user

    if not hasattr(user, 'supportmember'):
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not from support!'})

    if not user.supportmember.is_head:
        return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'You are not head of support!'})
    data = []
    merchants = Merchant.objects.all()
    for merchant in merchants:
        fee_objs = MerchantSolution.objects.filter(merchant=merchant, status=1)
        fees = MerchantSolutionSerializer(fee_objs, many=True)
        merchant_data = {'merchant_id': merchant.id, 'username': merchant.user.username, 'fees': fees.data}
        data.append(merchant_data)

    return Response(status=status.HTTP_200_OK, data=data)


@api_view(['GET'])
@permission_classes([HeadSupportPermission | DebugPermission])
def get_solution_creation_data(request, *args, **kwargs):
    payment_systems = PaymentSystem.objects.all()
    traffic_types = TrafficType.objects.all()

    data = dict()
    data["payment_systems"] = PaymentSystemSerializer(data=payment_systems, many=True).data
    data["traffic_types"] = TrafficTypeSerializer(data=traffic_types, many=True).data
    return Response(status=status.HTTP_200_OK, data=data)

