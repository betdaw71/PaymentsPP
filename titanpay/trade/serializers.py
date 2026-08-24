from rest_framework import serializers
from django.core.validators import MinValueValidator
from basics.models import PaymentSystem, PaymentDetails
from basics.serializers import PaymentDetailsSberActionSerializer, PaymentDetailsSberOrderSerializer, \
    PaymentDetailsSberPayOrderSerializer, PaymentDetailsSBPOrderSerializer, PaymentDetailsSberDepOrderSerializer
from merchant.models import Merchant
from titanpay.settings import (
    SBER_NAME,
    SBERPAY_NAME,
    SBP_NAME,
    SBERDEP_NAME,
    UPI_INTENT_NAME,
    C2C_NAME,
    PROTOCOL_C2C_NAME,
    C2CTRY_NAME,
    PLUTUS_TEST_PS_NAME,
    CONCORDED_KBZPAY_PS_NAME,
    CONCORDED_WAVEPAY_PS_NAME,
)
from trade.models import TransactionType, OutOrderStatus, InOrderStatus, InOrder, Transaction, WithdrawalRequest, \
    OutOrder, InOrderStatusChange
from rest_framework.exceptions import ValidationError


def payment_details_payload_for_order(payment_details, payment_system_name: str) -> dict:
    """Реквизит в ответе списка ордеров: имя PS из UPI_INTENT_NAME (settings) — как карта Сбера."""
    if payment_details is None:
        return {}
    card_ps = {SBER_NAME, UPI_INTENT_NAME, C2C_NAME, PROTOCOL_C2C_NAME}
    test_ps = (PLUTUS_TEST_PS_NAME or "").strip()
    if test_ps:
        card_ps.add(test_ps)
    if payment_system_name in card_ps:
        return PaymentDetailsSberOrderSerializer(payment_details).data
    if payment_system_name in (SBERDEP_NAME, C2CTRY_NAME):
        return PaymentDetailsSberDepOrderSerializer(payment_details).data
    if payment_system_name == SBERPAY_NAME:
        return PaymentDetailsSberPayOrderSerializer(payment_details).data
    if payment_system_name == SBP_NAME:
        return PaymentDetailsSBPOrderSerializer(payment_details).data
    if payment_system_name == "SIM":
        return PaymentDetailsSBPOrderSerializer(payment_details).data
    raise ValidationError("Not supported system!")


def payment_details_payload_for_in_order(in_order) -> dict:
    """PSP pay-in (Playments): реквизиты из сессии провайдера, не из виртуальной карты."""
    if in_order is None:
        return {}
    from payments.models import PayIn
    from payments.psp_payin import requisite_for_payin, requisite_payload_has_fields

    pay_in = PayIn.objects.filter(order_id=in_order.pk).first()
    if pay_in is not None:
        req = requisite_for_payin(pay_in)
        if requisite_payload_has_fields(req):
            return req
    ps_name = in_order.solution.payment_system.name if in_order.solution and in_order.solution.payment_system else ""
    concored_ps = {CONCORDED_KBZPAY_PS_NAME, CONCORDED_WAVEPAY_PS_NAME}
    if ps_name in concored_ps:
        return {}
    if in_order.payment_details is None:
        return {}
    return payment_details_payload_for_order(in_order.payment_details, ps_name)


class TransactionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionType
        fields = "__all__"


class OutOrderStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutOrderStatus
        fields = "__all__"


class InOrderStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = InOrderStatus
        fields = "__all__"


class InOrderTraderListSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = InOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'auto_closed']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name

        money_sent_status_change = InOrderStatusChange.objects.filter(status__name="Money sent by user", order=instance)
        if instance.status.name == 'New':
            representation['expires_at'] = (
                        instance.solution.payment_system.expired_time_in + instance.creation_date).timestamp()
        elif money_sent_status_change.exists():
            representation['expires_at'] = (
                        instance.solution.payment_system.expired_time_in + money_sent_status_change.first().created_at).timestamp()
        else:
            representation['expires_at'] = 0
        return representation


class InOrderTraderFullSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = InOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'auto_closed', 'trader_fee', 'pic', 'rejection_reason']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        representation['owner'] = instance.payment_details.group.owner

        money_sent_status_change = InOrderStatusChange.objects.filter(status__name="Money sent by user", order=instance)
        if instance.status.name == 'New':
            representation['expires_at'] = (
                        instance.solution.payment_system.expired_time_in + instance.creation_date).timestamp()
        elif money_sent_status_change.exists():
            representation['expires_at'] = (
                        instance.solution.payment_system.expired_time_in + money_sent_status_change.first().created_at).timestamp()
        else:
            representation['expires_at'] = 0
        return _attach_pic_url(representation, instance)


class InOrderTraderBossListSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = InOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'auto_closed']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['trader'] = instance.payment_details.group.trader.user.username

        money_sent_status_change = InOrderStatusChange.objects.filter(status__name="Money sent by user", order=instance)
        if instance.status.name == 'New':
            representation['expires_at'] = (instance.solution.payment_system.expired_time_in + instance.creation_date).timestamp()
        elif money_sent_status_change.exists():
            representation['expires_at'] = (instance.solution.payment_system.expired_time_in + money_sent_status_change.first().created_at).timestamp()
        else:
            representation['expires_at'] = 0
        return representation


class InOrderTraderBossFullSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = InOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'auto_closed', 'trader_fee', 'pic', 'rejection_reason']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        representation['trader'] = instance.payment_details.group.trader.user.username
        representation['owner'] = instance.payment_details.group.owner
        representation['payment_details_id'] = str(
            instance.payment_details.id) if instance.payment_details is not None else ''

        money_sent_status_change = InOrderStatusChange.objects.filter(status__name="Money sent by user", order=instance)
        if instance.status.name == 'New':
            representation['expires_at'] = (
                        instance.solution.payment_system.expired_time_in + instance.creation_date).timestamp()
        elif money_sent_status_change.exists():
            representation['expires_at'] = (
                        instance.solution.payment_system.expired_time_in + money_sent_status_change.first().created_at).timestamp()
        else:
            representation['expires_at'] = 0
        return _attach_pic_url(representation, instance)


def _attach_psp_reference(representation: dict, in_order) -> dict:
    from payments.models import PayIn
    from payments.psp_payin import psp_external_reference

    pay_in = PayIn.objects.filter(order_id=in_order.pk).first()
    representation["pay_in_id"] = str(pay_in.id) if pay_in else ""
    ref = psp_external_reference(pay_in) if pay_in else None
    representation["psp_provider"] = ref["psp_provider"] if ref else ""
    representation["psp_provider_order_id"] = ref["psp_provider_order_id"] if ref else ""
    return representation


def _attach_pic_url(representation: dict, instance) -> dict:
    from payments.models import PayIn
    from payments.utils import public_storage_url

    pic = (getattr(instance, "pic", None) or "").strip()
    if not pic:
        pay_in = PayIn.objects.filter(order_id=instance.pk).first()
        if pay_in:
            try:
                from appeals.models import PayInAppeal

                appeal = (
                    PayInAppeal.objects.filter(pay_in=pay_in)
                    .exclude(receipt_url="")
                    .order_by("-created_at")
                    .first()
                )
                if appeal:
                    pic = appeal.receipt_url
            except Exception:
                pass
    if pic:
        representation["pic"] = public_storage_url(pic)
    return representation


class InOrderSupportListSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = InOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'auto_closed', 'merchant_order_id']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        representation['trader'] = instance.payment_details.group.trader.user.username if instance.payment_details is not None else None
        representation['owner'] = instance.payment_details.group.owner if instance.payment_details is not None else None
        representation['merchant'] = instance.solution.merchant.user.username if instance.solution is not None else None
        # representation['customer_id'] = instance.pay_in.get().client.client_id
        # representation['customer_id'] = "000303033"

        money_sent_status_change = InOrderStatusChange.objects.filter(status__name="Money sent by user", order=instance)
        if instance.status.name == 'New':
            representation['expires_at'] = (
                        instance.solution.payment_system.expired_time_in + instance.creation_date).timestamp()
        elif money_sent_status_change.exists():
            representation['expires_at'] = (
                        instance.solution.payment_system.expired_time_in + money_sent_status_change.first().created_at).timestamp()
        else:
            representation['expires_at'] = 0
        return _attach_psp_reference(representation, instance)


class InOrderSupportSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = InOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'auto_closed', 'trader_fee', 'merchant_fee', 'merchant_order_id', 'pic', 'recalculated_amount', 'rejection_reason']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        representation['trader'] = instance.payment_details.group.trader.user.username if instance.payment_details is not None else None
        representation['owner'] = instance.payment_details.group.owner if instance.payment_details is not None else None
        representation['merchant'] = instance.solution.merchant.user.username if instance.solution is not None else None
        representation['payment_details_id'] = str(
            instance.payment_details.id) if instance.payment_details is not None else ''
        representation['customer_id'] = instance.pay_in.get().client.client_id
        # representation['customer_id'] = "000303033"

        money_sent_status_change = InOrderStatusChange.objects.filter(status__name="Money sent by user", order=instance)
        if instance.status.name == 'New':
            representation['expires_at'] = (
                        instance.solution.payment_system.expired_time_in + instance.creation_date).timestamp()
        elif money_sent_status_change.exists():
            representation['expires_at'] = (
                        instance.solution.payment_system.expired_time_in + money_sent_status_change.first().created_at).timestamp()
        else:
            representation['expires_at'] = 0
        representation = _attach_psp_reference(representation, instance)
        return _attach_pic_url(representation, instance)


class InOrderMerchantListSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = InOrder
        fields = ['id', 'creation_date', 'status', 'amount', 'usd_amount', 'payment_details', 'merchant_fee', 'merchant_order_id']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        # representation['customer_id'] = instance.pay_in.get().client.client_id
        # representation['customer_id'] = "000303033"
        return representation


class InOrderMerchantSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = InOrder
        fields = ['id', 'creation_date', 'status', 'amount', 'usd_amount', 'payment_details', 'merchant_fee', 'merchant_order_id', 'pic', 'rejection_reason']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        representation['customer_id'] = instance.pay_in.get().client.client_id
        # representation['customer_id'] = "000303033"
        return _attach_pic_url(representation, instance)


class InOrderTeamLeadSerializer(serializers.ModelSerializer):

    class Meta:
        model = InOrder
        fields = ['id', 'creation_date', 'status', 'amount', 'usd_amount', 'trader_fee']
        read_only_fields = ['amount', 'usd_amount']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        return representation


class InOrderCreateSerializer(serializers.ModelSerializer):
    payment_system = serializers.PrimaryKeyRelatedField(queryset=PaymentSystem.objects.all())
    merchant = serializers.PrimaryKeyRelatedField(queryset=Merchant.objects.all())

    class Meta:
        model = InOrder
        fields = ('amount', 'payment_system', 'merchant', 'merchant_order_id')


class OutOrderTraderListSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = OutOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'destination_details', 'auto_closed']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name

        money_sent_status = InOrderStatus.objects.get(name="Money sent by user")
        status_change = InOrderStatusChange.objects.filter(status=money_sent_status, order=instance)
        if status_change.exists():
            representation['expires_at'] = (instance.solution.payment_system.expired_time_in + status_change.first().created_at).timestamp()
        else:
            representation['expires_at'] = 0
        return representation


class OutOrderTraderFullSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = OutOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'destination_details', 'trader_fee', 'auto_closed', 'pic',  'sms_sent', 'pdf_sent', 'pdf_comment']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_details_id'] = str(instance.payment_details.id) if instance.payment_details is not None else ''
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        representation['owner'] = instance.payment_details.group.owner
        representation['expires_at'] = (instance.solution.payment_system.expired_time_out + instance.creation_date).timestamp()
        return _attach_pic_url(representation, instance)


class OutOrderTraderBossListSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = OutOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'destination_details']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['trader'] = instance.payment_details.group.trader.user.username if instance.payment_details is not None else None
        representation['expires_at'] = (instance.solution.payment_system.expired_time_out + instance.creation_date).timestamp()
        return representation


class OutOrderTraderBossFullSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = OutOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'auto_closed', 'trader_fee', 'destination_details', 'pic', 'rejection_reason', 'sms_sent', 'pdf_sent', 'pdf_comment']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        representation['payment_details_id'] = str(instance.payment_details.id) if instance.payment_details is not None else ''
        representation['trader'] = instance.payment_details.group.trader.user.username if instance.payment_details is not None else None
        representation['owner'] = instance.payment_details.group.owner if instance.payment_details is not None else None
        representation['expires_at'] = (instance.solution.payment_system.expired_time_out + instance.creation_date).timestamp()
        return _attach_pic_url(representation, instance)


class OutOrderSupportListSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = OutOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'auto_closed', 'trader_fee', 'merchant_fee', 'merchant_order_id', 'destination_details', 'rejection_reason']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        representation['trader'] = instance.payment_details.group.trader.user.username if instance.payment_details is not None else None
        representation['owner'] = instance.payment_details.group.owner if instance.payment_details is not None else None
        representation['merchant'] = instance.solution.merchant.user.username if instance.solution is not None else None
        # representation['customer_id'] = "000303033"
        # representation['customer_id'] = instance.pay_out.get().client.client_id
        representation['expires_at'] = (instance.solution.payment_system.expired_time_out + instance.creation_date).timestamp()

        return representation


class OutOrderSupportSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = OutOrder
        fields = ['id', 'creation_date', 'status', 'completion_date', 'amount', 'usd_amount', 'payment_details', 'auto_closed', 'trader_fee', 'merchant_fee', 'merchant_order_id', 'destination_details', 'pic', 'rejection_reason', 'sms_sent', 'pdf_sent', 'pdf_comment', 'recalculated_amount']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        representation['trader'] = instance.payment_details.group.trader.user.username if instance.payment_details is not None else None
        representation['owner'] = instance.payment_details.group.owner if instance.payment_details is not None else None
        representation['merchant'] = instance.solution.merchant.user.username if instance.solution is not None else None
        representation['payment_details_id'] = str(instance.payment_details.id) if instance.payment_details is not None else ''
        # representation['customer_id'] = "000303033"
        representation['customer_id'] = instance.pay_out.get().client.client_id if instance.pay_out.exists() else None
        representation['expires_at'] = (instance.solution.payment_system.expired_time_out + instance.creation_date).timestamp()

        return _attach_pic_url(representation, instance)


class OutOrderMerchantListSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = OutOrder
        fields = ['id', 'creation_date', 'status', 'amount', 'usd_amount', 'payment_details', 'merchant_fee', 'merchant_order_id', 'destination_details', 'pic']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        # representation['customer_id'] = instance.pay_out.get().client.client_id
        # representation['customer_id'] = "000303033"
        return _attach_pic_url(representation, instance)


class OutOrderMerchantSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = OutOrder
        fields = ['id', 'creation_date', 'status', 'amount', 'usd_amount', 'payment_details', 'merchant_fee', 'merchant_order_id', 'destination_details', 'pic']
        read_only_fields = ['amount', 'usd_amount']

    def get_payment_details(self, obj):
        return payment_details_payload_for_in_order(obj)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        representation['customer_id'] = instance.pay_out.get().client.client_id if instance.pay_out.exists() else None
        # representation['customer_id'] = "000303033"
        return _attach_pic_url(representation, instance)


class OutOrderTeamLeadSerializer(serializers.ModelSerializer):

    class Meta:
        model = InOrder
        fields = ['id', 'creation_date', 'status', 'amount', 'usd_amount', 'trader_fee']
        read_only_fields = ['amount', 'usd_amount']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.solution.payment_system.currency.symbol
        representation['payment_system'] = instance.solution.payment_system.name
        representation['traffic_type'] = instance.solution.traffic.name
        return representation


class OutOrderCreateSerializer(serializers.ModelSerializer):
    payment_system = serializers.PrimaryKeyRelatedField(queryset=PaymentSystem.objects.all())
    merchant = serializers.PrimaryKeyRelatedField(queryset=Merchant.objects.all())

    class Meta:
        model = OutOrder
        fields = ('amount', 'payment_system', 'merchant', 'merchant_order_id', 'client_ip', 'destination_details')


class OutOrderCheckSerializer(serializers.ModelSerializer):

    class Meta:
        model = OutOrder
        fields = ('id', 'amount', 'payment_details', 'destination_details')

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['payment_system'] = instance.solution.payment_system.name
        representation['payment_details'] = {'deposit_number': instance.payment_details.deposit_number[:4]}
        return representation


class TransactionMerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['transaction_type'] = instance.transaction_type.name
        user = self.context['request'].user
        user_balance = user.merchant.balance
        representation['is_incoming'] = instance.is_incoming(user_balance)
        return representation


class TransactionSubMerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['transaction_type'] = instance.transaction_type.name
        user = self.context['request'].user
        user_balance = user.submerchant.merchant.balance
        representation['is_incoming'] = instance.is_incoming(user_balance)
        return representation


class TransactionTeamLeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['transaction_type'] = instance.transaction_type.name
        user = self.context['request'].user
        user_balance = user.teamlead.balance
        representation['is_incoming'] = instance.is_incoming(user_balance)
        return representation


class TransactionTraderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['transaction_type'] = instance.transaction_type.name
        user = self.context['request'].user
        user_balance = user.trader.balance_usdt
        representation['is_incoming'] = instance.is_incoming(user_balance)
        return representation


class TransactionSupportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['transaction_type'] = instance.transaction_type.name
        representation["from"] = instance.get_from()
        representation["to"] = instance.get_to()
        return representation


class WithdrawalRequestBasicSerializer(serializers.ModelSerializer):

    class Meta:
        model = WithdrawalRequest
        fields = ['id', 'status', 'amount', 'address_to', 'comment', 'date']


class WithdrawalRequestSupportSerializer(serializers.ModelSerializer):

    class Meta:
        model = WithdrawalRequest
        fields = '__all__'

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['from_user'] = instance.from_user.username

        return representation


class WithdrawalRequestCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=32, decimal_places=2, validators=[MinValueValidator(0)])
    address = serializers.CharField(max_length=42)


class WithdrawalRequestApproveSerializer(serializers.Serializer):
    tx_id = serializers.CharField(max_length=255)


class WithdrawalRequestRejectSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=255)


class TransactionIdSerializer(serializers.Serializer):
    transaction_id = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)


class CommentSerializer(serializers.Serializer):
    trader_comment = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)


class MoveSerializer(serializers.Serializer):
    details = serializers.PrimaryKeyRelatedField(queryset=PaymentDetails.objects.all())


class RecalculateTraderSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=32, decimal_places=2, validators=[MinValueValidator(0)])
    file = serializers.FileField()


class RecalculateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=32, decimal_places=2, validators=[MinValueValidator(0)])
