from rest_framework import serializers

from django.db import transaction
from django.utils import timezone

from basics.models import PaymentDetails
from payments.models import PayIn, Currency, PaymentSystem, APIKeys, PayInStatus, PayOut, PayOutStatus, Client
from rest_framework.authtoken.models import Token
from trade.models import InOrder, OutOrder, OutOrderStatus, TransactionType, Transaction
from merchant.models import MerchantSolution
from rest_framework.exceptions import ValidationError
from payments.utils2 import (
    get_client_object,
    check_pending,
    assert_payin_amount_within_solution,
    is_placeholder_client_email,
)
from payments.utils import generate_link, translate_bank
from trade.serializers import PaymentDetailsSberActionSerializer
from titanpay.settings import SBER_NAME, SBERPAY_NAME, SBP_NAME, SBERDEP_NAME, C2C_NAME, PROTOCOL_C2C_NAME, C2CTRY_NAME


def get_in_ps_serializer(payment_system_name):
    if payment_system_name in (SBER_NAME, C2C_NAME, PROTOCOL_C2C_NAME):
        return PaymentDetailsCardSerializer
    elif payment_system_name in (SBERDEP_NAME, C2CTRY_NAME):
        return PaymentDetailsSberDepSerializer
    elif payment_system_name == SBERPAY_NAME:
        return PaymentDetailsSberPaySerializer
    elif payment_system_name == SBP_NAME:
        return PaymentDetailsSBPSerializer


class CurrencySymbolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ['symbol']


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['client_id', 'email', 'phone', 'name']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if is_placeholder_client_email(data.get("email"), data.get("client_id")):
            data["email"] = None
        return data


def resolve_currency_and_payment_system_ids(data: dict) -> dict:
    """Регистронезависимый разбор currency / payment_system из тела запроса мерчанта."""
    currency_symbol = (data.get('currency') or '').strip()
    payment_system_name = (data.get('payment_system') or '').strip()
    try:
        currency = Currency.objects.get(symbol__iexact=currency_symbol)
        payment_system = PaymentSystem.objects.filter(
            name__iexact=payment_system_name,
            currency=currency,
        ).first()
        if payment_system is None:
            raise PaymentSystem.DoesNotExist
        data = dict(data)
        data['currency'] = currency.id
        data['payment_system'] = payment_system.id
    except Currency.DoesNotExist:
        raise serializers.ValidationError({"currency": "Currency with this symbol does not exist"})
    except PaymentSystem.DoesNotExist:
        raise serializers.ValidationError({"payment_system": "Payment System with this name does not exist"})
    return data


class PayInInvoiceCreateSerializer(serializers.ModelSerializer):
    ftd = serializers.BooleanField(required=True, write_only=True)
    client = ClientSerializer()
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = PayIn
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'merchant_order_id', 'success_url',
                  'failed_url', 'callback_url', 'created_at', 'updated_at', 'payment_details', 'client', 'ftd']
        read_only_fields = ['created_at', 'updated_at', 'status']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['expires_at'] = int((instance.created_at + instance.payment_system.expired_time_in).timestamp())
        representation['recalculated'] = instance.order.recalculated
        representation['redirect_url'] = generate_link(instance.id, instance.payment_system.name)
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        from payments.psp_payin import enrich_payin_payment_details as enrich_psp

        return enrich_psp(representation, instance)

    def to_internal_value(self, data):
        data = resolve_currency_and_payment_system_ids(data)
        return super().to_internal_value(data)

    def get_payment_details(self, obj):
        from payments.psp_payin import requisite_for_payin

        req = requisite_for_payin(obj)
        if req is not None:
            return req
        if obj.order.payment_details is not None:
            serializer_cls = get_in_ps_serializer(obj.payment_system.name)
            if serializer_cls is not None:
                return serializer_cls(obj.order.payment_details).data
        return {}

    def create(self, validated_data):
        merchant = self.context['request'].user.merchant
        payin_status = PayInStatus.objects.get(name="In Progress")

        ftd = validated_data.pop('ftd', None)

        if ftd is None:
            raise serializers.ValidationError({"ftd": "This field is required"})

        solution = MerchantSolution.objects.filter(merchant=merchant, payment_system=validated_data['payment_system'], ftd=ftd, status=1)

        if not solution.exists():
            raise ValidationError({"error": "This method is not active"})

        solution = solution.first()

        assert_payin_amount_within_solution(solution, validated_data['amount'])

        if InOrder.objects.filter(solution__merchant=merchant,
                                  merchant_order_id=validated_data.get('merchant_order_id')).exists():
            raise ValidationError({"error": "Order with such merchant_order_id already exists "})

        if OutOrder.objects.filter(solution__merchant=merchant,
                                   merchant_order_id=validated_data.get('merchant_order_id')).exists():
            raise ValidationError({"error": "Order with such merchant_order_id already exists "})

        client, success = get_client_object(validated_data['client'], merchant)

        if not success:
            raise ValidationError({"error": "Client is blacklisted"})

        client_deposit_count = client.order_count

        pending_exits = check_pending(client, _in=True)

        if pending_exits:
            raise ValidationError({"error": "Client has a pending pay-in"})

        in_order = InOrder.create(amount=validated_data['amount'], solution=solution, client_deposit_count=client_deposit_count, merchant_order_id=validated_data['merchant_order_id'])

        pay_in = PayIn.objects.create(amount=validated_data['amount'], currency=validated_data['currency'],
                                      payment_system=validated_data['payment_system'],
                                      merchant_order_id=validated_data['merchant_order_id'],
                                      success_url=validated_data.get('success_url'),
                                      failed_url=validated_data.get('failed_url'),
                                      callback_url=validated_data['callback_url'], merchant=merchant, order=in_order,
                                      status=payin_status, client=client)
        from payments.payin_trace import trace_routing_result

        trace_routing_result(pay_in, in_order)
        if in_order.status.name == "Cannot process":
            from payments.psp_payin import decline_payin

            decline_payin(pay_in, send_callback=False)
            return pay_in
        from payments.psp_payin import try_attach_psp_sessions

        try_attach_psp_sessions(pay_in)
        pay_in.refresh_from_db()
        return pay_in


class PaymentDetailsCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentDetails
        fields = ['card_number']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['bank'] = translate_bank(instance.group.payment_system.name)
        representation['owner'] = instance.group.owner
        return representation


class PaymentDetailsSberPaySerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentDetails
        fields = ['phone']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['bank'] = translate_bank(instance.group.payment_system.name)
        representation['owner'] = instance.group.owner
        return representation


class PaymentDetailsSBPSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentDetails
        fields = ['phone']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['bank'] = translate_bank(instance.group.payment_system.name)
        representation['owner'] = instance.group.owner
        return representation


class PaymentDetailsSberDepSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentDetails
        fields = ['deposit_number']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['bic'] = instance.group.bic
        representation['owner'] = instance.group.owner
        return representation


class PayInInvoiceRetrieveSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = PayIn
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'payment_details', 'success_url', 'failed_url']

    def get_payment_details(self, obj):
        from payments.psp_payin import requisite_for_payin

        req = requisite_for_payin(obj)
        if req is not None:
            return req
        if obj.order.payment_details is not None:
            serializer_cls = get_in_ps_serializer(obj.payment_system.name)
            if serializer_cls is not None:
                return serializer_cls(obj.order.payment_details).data
        return {}

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['expires_at'] = int((instance.created_at + instance.payment_system.expired_time_in).timestamp())
        representation['arbitrage'] = instance.order.status.name == "Arbitrage" if instance.order is not None else False
        representation['recalculated'] = instance.order.recalculated if instance.order is not None else False
        representation['waiting_confirmation'] = (
            instance.order.status.name in ("Money sent by user", "Arbitrage")
            if instance.order and instance.order.status
            else False
        )
        representation['order_status'] = (
            instance.order.status.name if instance.order and instance.order.status else None
        )
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        from payments.psp_payin import enrich_payin_payment_details as enrich_psp

        return enrich_psp(representation, instance)


class PayInInvoiceNewSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayIn
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'merchant_order_id']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        from payments.psp_payin import enrich_payin_payment_details as enrich_psp, requisite_for_payin

        req = requisite_for_payin(instance)
        if req:
            representation['payment_details'] = req
        elif instance.order and instance.order.payment_details is not None:
            serializer_cls = get_in_ps_serializer(instance.payment_system.name)
            representation['payment_details'] = (
                serializer_cls(instance.order.payment_details).data if serializer_cls else {}
            )
        else:
            representation['payment_details'] = {}
        representation['expires_at'] = (instance.created_at + instance.payment_system.expired_time_in).timestamp()
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        return enrich_psp(representation, instance)


class PayInInvoiceInProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayIn
        fields = ['id', 'currency', 'amount', 'status', 'merchant_order_id', 'payment_system', 'success_url', 'failed_url']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        representation['waiting_confirmation'] = True
        representation['order_status'] = instance.order.status.name if instance.order and instance.order.status else None
        return representation


class PayInInvoiceSuccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayIn
        fields = ['id', 'currency', 'amount', 'status', 'merchant_order_id', 'success_url', 'payment_system']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        return representation


class PayInInvoiceFailSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayIn
        fields = ['id', 'currency', 'amount', 'status', 'merchant_order_id', 'failed_url']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        return representation


class PayInPaymentCreateSerializer(serializers.ModelSerializer):
    ftd = serializers.BooleanField(required=True, write_only=True)
    client = ClientSerializer()
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = PayIn
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'merchant_order_id', 'success_url',
                  'failed_url', 'callback_url', 'created_at', 'updated_at', 'payment_details', 'client', 'ftd']
        read_only_fields = ['created_at', 'updated_at', 'status']

    def to_internal_value(self, data):
        data = resolve_currency_and_payment_system_ids(data)
        return super().to_internal_value(data)

    def get_payment_details(self, obj):
        from payments.psp_payin import requisite_for_payin

        req = requisite_for_payin(obj)
        if req is not None:
            return req
        if obj.order.payment_details is not None:
            serializer_cls = get_in_ps_serializer(obj.payment_system.name)
            if serializer_cls is not None:
                return serializer_cls(obj.order.payment_details).data
        return {}

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['expires_at'] = int((instance.created_at + instance.payment_system.expired_time_in).timestamp())
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        from payments.psp_payin import enrich_payin_payment_details as enrich_psp

        return enrich_psp(representation, instance)

    def create(self, validated_data):
        merchant = self.context['request'].user.merchant
        payin_status = PayInStatus.objects.get(name="New")

        ftd = validated_data.pop('ftd', None)

        if ftd is None:
            raise serializers.ValidationError({"ftd": "This field is required"})

        solution = MerchantSolution.objects.filter(merchant=merchant, payment_system=validated_data['payment_system'], ftd=ftd, status=1)

        if not solution.exists():
            raise ValidationError({"error": "This method is not active"})

        if InOrder.objects.filter(solution__merchant=merchant,
                                  merchant_order_id=validated_data.get('merchant_order_id')).exists():
            raise ValidationError({"error": "Order with such merchant_order_id already exists "})

        if OutOrder.objects.filter(solution__merchant=merchant,
                                   merchant_order_id=validated_data.get('merchant_order_id')).exists():
            raise ValidationError({"error": "Order with such merchant_order_id already exists "})

        solution = solution.first()

        assert_payin_amount_within_solution(solution, validated_data['amount'])

        client, success = get_client_object(validated_data['client'], merchant)

        if not success:
            raise ValidationError({"error": "Client is blacklisted"})

        client_deposit_count = client.order_count

        pending_exits = check_pending(client, _in=True)

        if pending_exits:
            raise ValidationError({"error": "Client has a pending pay-in"})

        in_order = InOrder.create(amount=validated_data['amount'], solution=solution,
                                  client_deposit_count=client_deposit_count,
                                  merchant_order_id=validated_data['merchant_order_id'])

        pay_in = PayIn.objects.create(amount=validated_data['amount'], currency=validated_data['currency'],
                                      payment_system=validated_data['payment_system'],
                                      merchant_order_id=validated_data['merchant_order_id'],
                                      success_url=validated_data.get('success_url'),
                                      failed_url=validated_data.get('failed_url'),
                                      callback_url=validated_data['callback_url'], merchant=merchant, order=in_order,
                                      status=payin_status, client=client)
        from payments.payin_trace import trace_routing_result

        trace_routing_result(pay_in, in_order)
        if in_order.status.name == "Cannot process":
            from payments.psp_payin import decline_payin

            decline_payin(pay_in, send_callback=False)
            return pay_in
        from payments.psp_payin import try_attach_psp_sessions

        try_attach_psp_sessions(pay_in)
        pay_in.refresh_from_db()
        return pay_in


class PayInPaymentRetrieveSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = PayIn
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'merchant_order_id', 'status', 'created_at',
                  'updated_at', 'payment_details']

    def get_payment_details(self, obj):
        from payments.psp_payin import requisite_for_payin

        req = requisite_for_payin(obj)
        if req is not None:
            return req
        if obj.order.payment_details is not None:
            serializer_cls = get_in_ps_serializer(obj.payment_system.name)
            if serializer_cls is not None:
                return serializer_cls(obj.order.payment_details).data
        return {}

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['recalculated'] = instance.order.recalculated
        representation['expires_at'] = int((instance.created_at + instance.payment_system.expired_time_in).timestamp())
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        from payments.psp_payin import enrich_payin_payment_details as enrich_psp

        return enrich_psp(representation, instance)


class APIKeysCreateSerializer(serializers.ModelSerializer):
    token = serializers.SerializerMethodField()

    class Meta:
        model = APIKeys
        fields = ['id', 'token', 'private_key', 'created_at', 'whitelist_ips', 'whitelist_on']

    def get_token(self, obj):
        Token.objects.filter(user=obj.merchant.user).delete()
        token = Token.objects.create(user=obj.merchant.user)
        return token.key

    def create(self, validated_data):
        merchant = self.context['request'].user.merchant
        return APIKeys.create(merchant=merchant)


class APIKeysListSerializer(serializers.ModelSerializer):
    token = serializers.SerializerMethodField()

    class Meta:
        model = APIKeys
        fields = ['id', 'token', 'created_at', 'whitelist_ips', 'whitelist_on']

    def get_token(self, obj):
        token = Token.objects.get(user=obj.merchant.user)
        return token.key


class WhitelistSerializer(serializers.Serializer):
    whitelist_on = serializers.BooleanField(default=False)
    whitelist = serializers.JSONField(default=list())


class PayOutInvoiceCreateSerializer(serializers.ModelSerializer):
    ftd = serializers.BooleanField(required=True)
    client = serializers.SerializerMethodField()

    class Meta:
        model = PayOut
        fields = ['id', 'status', 'currency', 'amount', 'payment_system', 'merchant_order_id', 'success_url',
                  'failed_url', 'callback_url', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at', 'status']

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['status'] = instance.status.name if instance.status is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['redirect_url'] = generate_link(instance.id, _in=False)
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        return representation

    def to_internal_value(self, data):
        data = resolve_currency_and_payment_system_ids(data)
        return super().to_internal_value(data)

    def create(self, validated_data):
        merchant = self.context['request'].user.merchant
        payout_status = PayOutStatus.objects.get(name="New")

        ftd = validated_data.pop('ftd', None)

        if ftd is None:
            raise serializers.ValidationError({"error": "FTD field is required"})

        solution = MerchantSolution.objects.filter(merchant=merchant, payment_system=validated_data['payment_system'],
                                                   ftd=ftd, status=1)

        if not solution.exists():
            raise ValidationError({"error": "This method is not active"})

        client, success = get_client_object(validated_data['client'], merchant)

        if not success:
            raise ValidationError({"error": "Client is blacklisted"})

        pending_exits = check_pending(client, _in=False)

        if pending_exits:
            raise ValidationError({"error": "Client has a pending pay-out"})

        pay_out = PayOut.objects.create(amount=validated_data['amount'], currency=validated_data['currency'],
                                        payment_system=validated_data['payment_system'],
                                        merchant_order_id=validated_data['merchant_order_id'],
                                        success_url=validated_data['success_url'],
                                        failed_url=validated_data['failed_url'],
                                        callback_url=validated_data['callback_url'], merchant=merchant,
                                        status=payout_status)
        return pay_out


class PayOutInvoiceRetrieveSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayOut
        fields = ['id', 'currency', 'amount', 'payment_system', 'order_id', 'status', 'created_at', 'updated_at',
                  'merchant_order_id']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['status'] = instance.status.name if instance.status is not None else None
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        # representation['expires_at'] = (instance.created_at + instance.payment_system.expired_time_out).timestamp()
        return representation


class PayOutInvoiceNewSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayOut
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'merchant_order_id']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['required_fields'] = instance.payment_system.required_fields
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['expires_at'] = int((instance.created_at + instance.payment_system.expired_time_out).timestamp())
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        return representation


class PayOutInvoiceInProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayOut
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'merchant_order_id', 'details']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        return representation


class PayOutInvoiceSuccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayOut
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'merchant_order_id', 'success_url']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        return representation


class PayOutInvoiceFailSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayOut
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'merchant_order_id', 'failed_url']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['status'] = instance.status.name
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        return representation


class PayOutPaymentCreateSerializer(serializers.ModelSerializer):
    ftd = serializers.BooleanField(required=True, write_only=True)
    client = ClientSerializer(required=True)

    class Meta:
        model = PayOut
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'merchant_order_id', 'success_url',
                  'failed_url', 'callback_url', 'created_at', 'updated_at', 'details', 'ftd', 'client']
        read_only_fields = ['created_at', 'updated_at', 'status']

    def to_internal_value(self, data):
        data = resolve_currency_and_payment_system_ids(data)

        if data.get('details') is None:
            raise serializers.ValidationError({"details": "This field is required"})

        return super().to_internal_value(data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['status'] = instance.status.name if instance.status is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['expires_at'] = int((instance.created_at + instance.payment_system.expired_time_out).timestamp())
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        return representation

    def create(self, validated_data):
        merchant = self.context['request'].user.merchant
        payout_status = PayOutStatus.objects.get(name="New")

        ftd = validated_data.pop('ftd', None)

        if ftd is None:
            raise serializers.ValidationError({"error": "FTD field is required"})

        solution = MerchantSolution.objects.filter(merchant=merchant, payment_system=validated_data['payment_system'],
                                                   ftd=ftd, status=1)

        if not solution.exists():
            raise ValidationError({"error": "This method is not active"})

        if InOrder.objects.filter(solution__merchant=merchant, merchant_order_id=validated_data.get('merchant_order_id')).exists():
            raise ValidationError({"error": "Order with such merchant_order_id already exists "})

        if OutOrder.objects.filter(solution__merchant=merchant, merchant_order_id=validated_data.get('merchant_order_id')).exists():
            raise ValidationError({"error": "Order with such merchant_order_id already exists "})

        solution = solution.first()

        if not solution.min_limit_out <= validated_data['amount'] <= solution.max_limit_out:
            raise ValidationError({"error": "Amount out of limits!"})

        client, success = get_client_object(validated_data['client'], merchant)

        if not success:
            raise ValidationError({"error": "Client is blacklisted"})

        pending_exits = check_pending(client, _in=False)

        if pending_exits:
            raise ValidationError({"error": "Client has a pending pay-out"})
        try:
            out_order = OutOrder.create(amount=validated_data['amount'],
                                        merchant_order_id=validated_data['merchant_order_id'],
                                        details=validated_data['details'], solution=solution)
        except ValidationError as e:
            raise ValidationError(e)
        pay_out = PayOut.objects.create(amount=validated_data['amount'], currency=validated_data['currency'],
                                        payment_system=validated_data['payment_system'],
                                        merchant_order_id=validated_data['merchant_order_id'],
                                        success_url=validated_data.get('success_url'),
                                        failed_url=validated_data.get('failed_url'),
                                        callback_url=validated_data['callback_url'], merchant=merchant, order=out_order,
                                        status=payout_status, details=validated_data['details'], client=client)
        if out_order.status.name == "Cannot process":
            pay_out.declined()
            return pay_out

        from payments.playments_client import try_create_playments_payout
        from trade.utils import get_client_ip

        request = self.context.get("request")
        client_ip = get_client_ip(request) if request is not None else None
        playments_ok = try_create_playments_payout(pay_out, client_ip=client_ip)
        if playments_ok is False:
            with transaction.atomic():
                od = OutOrder.objects.select_for_update().get(pk=out_order.pk)
                if od.status and od.status.name == "New":
                    od.unfreeze("Playments withdrawal create failed")
                    od.decrease_current_volume()
                    od.status = OutOrderStatus.objects.get(name="Cannot process")
                    od.updated_date = timezone.now()
                    od.save(update_fields=["status", "updated_date"])
            pay_out.declined()
            return pay_out

        pay_out.in_progress()
        return pay_out


class PayOutPaymentRetrieveSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayOut
        fields = ['id', 'currency', 'amount', 'payment_system', 'status', 'merchant_order_id', 'status', 'created_at', 'updated_at']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['currency'] = instance.currency.symbol if instance.currency is not None else None
        representation['payment_system'] = instance.payment_system.name if instance.payment_system is not None else None
        representation['status'] = instance.status.name if instance.status is not None else None
        representation['recalculated'] = instance.order.recalculated
        representation['usd_amount'] = float(instance.order.usd_amount) if instance.order is not None else None
        return representation


class PaymentSystemMerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentSystem
        fields = ['name', 'currency', 'required_fields']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['currency'] = instance.currency.symbol
        return representation