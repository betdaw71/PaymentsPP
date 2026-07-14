from trade.models import OutOrder
from rest_framework import serializers

from basics.models import PaymentSystem, PaymentDetails
from basics.serializers import PaymentDetailsSberActionSerializer
from merchant.models import Merchant
from titanpay.settings import SBER_NAME
from trade.models import TransactionType, OutOrderStatus, InOrderStatus, InOrder, Transaction, WithdrawalRequest, \
    OutOrder, InOrderStatusChange
from rest_framework.exceptions import ValidationError


class OutOrderBotSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = OutOrder
        fields = ['id', 'amount', 'payment_details', 'destination_details']

    def get_payment_details(self, obj):
        return PaymentDetailsSberActionSerializer(obj.payment_details).data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['owner'] = instance.payment_details.group.owner if instance.payment_details is not None else None
        representation['expires_at'] = (instance.solution.payment_system.expired_time_out + instance.creation_date).timestamp()
        return representation




