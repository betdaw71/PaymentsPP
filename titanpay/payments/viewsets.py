from io import BytesIO

from payments.models import PayIn, PayOut
from payments.serializers import PayInInvoiceCreateSerializer, PayInInvoiceRetrieveSerializer, \
    PayInPaymentCreateSerializer, PayInPaymentRetrieveSerializer, APIKeysCreateSerializer, APIKeysListSerializer, \
    PayOutInvoiceCreateSerializer, PayOutInvoiceRetrieveSerializer, PayOutPaymentRetrieveSerializer, \
    PayOutPaymentCreateSerializer, PayInInvoiceNewSerializer, PayInInvoiceInProgressSerializer, \
    PayInInvoiceSuccessSerializer, PayInInvoiceFailSerializer, PayOutInvoiceNewSerializer, \
    PayOutInvoiceInProgressSerializer, PayOutInvoiceFailSerializer, \
    PayOutInvoiceSuccessSerializer, CurrencySymbolSerializer, WhitelistSerializer
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework import viewsets, status
from basics.permissions import MerchantPermission
from rest_framework.permissions import IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from payments.models import Currency, PayIn, PaymentSystem, APIKeys
from rest_framework.decorators import action
from basics.paginators import StandardResultsSetPagination
from payments.utils import upload_to_s3
from trade.models import OutOrder, TransactionType, Transaction, InOrder
from trade.serializers import TransactionIdSerializer
from trade.utils import get_client_ip
from payments.serializers import PaymentSystemMerchantSerializer
from django.db import transaction
from payments.psp_payin import cancel_psp_if_linked


class APIKeysViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    permission_classes = [MerchantPermission | IsAdminUser]
    http_method_names = ['post', 'get']

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'merchant'):
            merchant = user.merchant
            return APIKeys.objects.filter(merchant=merchant, active=True)
        return APIKeys.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return APIKeysCreateSerializer
        if self.action == 'list':
            return APIKeysListSerializer
        return APIKeysListSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        user = self.request.user
        if hasattr(user, 'merchant'):
            merchant = user.merchant
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)

        obj = APIKeys.create(merchant=merchant)
        serializer = APIKeysCreateSerializer(obj)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(methods=['POST'], detail=True, url_path='whitelist', permission_classes=[MerchantPermission])
    def upd_whitelist(self, request, id=None):
        serializer = WhitelistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        keys = APIKeys.objects.filter(id=id)
        if not keys.exists():
            return Response(status=status.HTTP_404_NOT_FOUND)
        keys = keys.first()
        if request.user != keys.merchant.user:
            return Response(status=status.HTTP_403_FORBIDDEN)

        keys.update_whitelist(data['whitelist_on'], data['whitelist'])
        return Response(status=status.HTTP_200_OK)


class PayInInvoiceViewset(viewsets.ModelViewSet):  # for redirect
    lookup_field = 'id'
    permission_classes = [MerchantPermission | IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['post', 'get']
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'merchant'):
            merchant = user.merchant
            return PayIn.objects.filter(merchant=merchant)
        if user.is_superuser:
            return PayIn.objects.all()
        return PayIn.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return PayInInvoiceCreateSerializer
        if self.action == 'retrieve' or self.action == 'list':
            return PayInInvoiceRetrieveSerializer
        return PayInInvoiceRetrieveSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if not instance.merchant == request.user.merchant:
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance)
        signature = request.user.merchant.api_keys.get(active=True).sign_data(serializer.data)
        headers = {"Signature": signature}
        return Response(serializer.data, headers=headers)

    def create(self, request, *args, **kwargs):
        from payments.payin_trace import wrap_merchant_payin_create

        return wrap_merchant_payin_create(self, request, *args, **kwargs)

    @action(detail=True, methods=['POST'], url_path='sent', permission_classes=[])
    def sent(self, request, id=None):
        if not PayIn.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'details': 'Order not found'})
        pay_in = PayIn.objects.get(id=id)

        try:
            with transaction.atomic():
                order = InOrder.objects.select_for_update().get(id=pay_in.order.id)
                order.change_to_money_sent_by_user()

        except ValidationError as e:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=e.detail
            )

        return Response(status=status.HTTP_200_OK, data={'success': True})

    @transaction.atomic
    @action(detail=True, methods=['POST'], url_path='arbitrage', permission_classes=[])
    def arbitrage(self, request, id=None):
        if not PayIn.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'details': 'Order not found'})

        pay_in = PayIn.objects.get(id=id)
        file = request.data.get('file')
        if not file:
            raise ValidationError("No file provided")

        if file.content_type not in ['image/png', 'image/jpeg', 'application/pdf']:
            return Response({'error': 'Unsupported file type. Only PNG, JPEG, and PDF are allowed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        file_prefix = file.content_type.split('/')[-1]
        object_name = f"in-{str(id)[:8]}.{file_prefix}"
        file_url = upload_to_s3(file, object_name)
        pay_in.order.pic = file_url
        pay_in.order.save()

        try:
            with transaction.atomic():
                order = InOrder.objects.select_for_update().get(id=pay_in.order.id)
                order.arbitrage()

        except ValidationError as e:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=e.detail
            )

        return Response(status=status.HTTP_200_OK, data={'success': True})

    @action(detail=True, methods=['POST'], url_path='cancel', permission_classes=[])
    def cancel(self, request, id=None):
        if not PayIn.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'details': 'Order not found'})
        pay_in = PayIn.objects.get(id=id)
        order = pay_in.order

        try:
            with transaction.atomic():
                order = InOrder.objects.select_for_update().get(id=order.id)
                order.cancel_order()

        except ValidationError as e:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=e.detail
            )

        cancel_psp_if_linked(pay_in)
        pay_in.refresh_from_db()

        data = {'status': pay_in.status.name}

        return Response(status=status.HTTP_200_OK, data=data)

    @action(detail=True, methods=['GET'], url_path='obtain', permission_classes=[])
    def obtain(self, request, id=None):
        if not PayIn.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'details': 'Order not found'})
        pay_in = PayIn.objects.select_related(
            "status", "currency", "payment_system", "order__status", "melbet_session"
        ).get(id=id)

        from payments.invoice_obtain import payin_invoice_obtain_serializer
        from payments.payment_page_enrich import enrich_for_payment_page, resolve_locale

        serializer = payin_invoice_obtain_serializer(pay_in)
        locale = resolve_locale(pay_in, request.GET.get("lang"))
        data = enrich_for_payment_page(serializer.data, pay_in, locale=locale)
        return Response(status=status.HTTP_200_OK, data=data)

    @action(detail=True, methods=['GET', 'POST'], url_path='complete', permission_classes=[])
    def complete(self, request, id=None):
        """Терминальный статус → URL для редиректа на сайт мерчанта."""
        if not PayIn.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'details': 'Order not found'})
        pay_in = PayIn.objects.select_related("status").get(id=id)
        status_name = pay_in.status.name if pay_in.status else ""

        if status_name == "Success":
            return Response(
                status=status.HTTP_200_OK,
                data={"status": status_name, "success_url": pay_in.success_url or ""},
            )
        if status_name in ("Failed", "Declined"):
            return Response(
                status=status.HTTP_200_OK,
                data={"status": status_name, "failed_url": pay_in.failed_url or ""},
            )
        return Response(status=status.HTTP_200_OK, data={"status": status_name})


class PayInPaymentViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    permission_classes = [MerchantPermission | IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['post', 'get']
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'merchant'):
            merchant = user.merchant
            return PayIn.objects.filter(merchant=merchant)
        if user.is_superuser:
            return PayIn.objects.all()
        return PayIn.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return PayInPaymentCreateSerializer
        if self.action == 'retrieve' or self.action == 'list':
            return PayInPaymentRetrieveSerializer
        return PayInPaymentRetrieveSerializer

    def create(self, request, *args, **kwargs):
        from payments.payin_trace import wrap_merchant_payin_create

        return wrap_merchant_payin_create(self, request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if not instance.merchant == request.user.merchant:
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance)
        signature = request.user.merchant.api_keys.get(active=True).sign_data(serializer.data)
        headers = {"Signature": signature}
        return Response(serializer.data, headers=headers)

    @action(detail=True, methods=['POST'], url_path='sent', permission_classes=[])
    def sent(self, request, id=None):
        if not PayIn.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'details': 'Order not found'})
        pay_in = PayIn.objects.get(id=id)

        try:
            with transaction.atomic():
                order = InOrder.objects.select_for_update().get(id=pay_in.order.id)
                order.change_to_money_sent_by_user()

        except ValidationError as e:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=e.detail
            )

        return Response(status=status.HTTP_200_OK, data={'success': True})

    @action(detail=True, methods=['POST'], url_path='arbitrage', permission_classes=[MerchantPermission])
    def arbitrage(self, request, id=None):

        if not PayIn.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})

        pay_in = PayIn.objects.filter(id=id).first()

        if not pay_in.merchant == request.user.merchant:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'Wrong order'})

        file = request.data.get('file')
        if not file:
            raise ValidationError("No file provided")

        if file.content_type not in ['image/png', 'image/jpeg', 'application/pdf']:
            return Response({'error': 'Unsupported file type. Only PNG, JPEG, and PDF are allowed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        file_prefix = file.content_type.split('/')[-1]
        object_name = f"in-{str(id)[:8]}.{file_prefix}"
        file_url = upload_to_s3(file, object_name)
        pay_in.order.pic = file_url
        pay_in.order.save()

        try:
            with transaction.atomic():
                order = InOrder.objects.select_for_update().get(id=pay_in.order.id)
                order.arbitrage()

        except ValidationError as e:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=e.detail
            )

        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=['POST'], url_path='cancel', permission_classes=[MerchantPermission])
    def cancel(self, request, id=None):

        if not PayIn.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'error': 'Order not found'})

        pay_in = PayIn.objects.filter(id=id).first()

        if not pay_in.merchant == request.user.merchant:
            return Response(status=status.HTTP_403_FORBIDDEN, data={'error': 'Wrong order'})

        try:
            with transaction.atomic():
                order = InOrder.objects.select_for_update().get(id=pay_in.order.id)
                order.cancel_order()

        except ValidationError as e:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=e.detail
            )

        cancel_psp_if_linked(pay_in)

        return Response(status=status.HTTP_200_OK)


class CurrenciesViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    serializer_class = CurrencySymbolSerializer
    queryset = Currency.objects.all()
    permission_classes = [MerchantPermission | IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = '__all__'
    search_fields = "__all__"
    ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['get']

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'merchant'):
            merchant = user.merchant
            ps = merchant.payment_systems.all()
            return Currency.objects.filter(paymentsystem__in=ps).distinct()
        if user.is_superuser:
            return Currency.objects.all()
        return Currency.objects.none()


class PaymentSystemsViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    serializer_class = PaymentSystemMerchantSerializer
    permission_classes = [MerchantPermission | IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    ordering = ['id']
    http_method_names = ['get']

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'merchant'):
            merchant = user.merchant
            return merchant.payment_systems.all()
        if user.is_superuser:
            return PaymentSystem.objects.all()
        return PaymentSystem.objects.none()


class PayOutInvoiceViewset(viewsets.ModelViewSet):  # for redirect
    lookup_field = 'id'
    permission_classes = [MerchantPermission | IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    # filterset_fields = '__all__'
    # search_fields = "__all__"
    # ordering_fields = "__all__"
    ordering = ['id']
    http_method_names = ['post', 'get']
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'merchant'):
            merchant = user.merchant
            return PayOut.objects.filter(merchant=merchant)
        if user.is_superuser:
            return PayOut.objects.all()
        return PayOut.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return PayOutInvoiceCreateSerializer
        if self.action == 'retrieve' or self.action == 'list':
            return PayOutInvoiceRetrieveSerializer
        return PayOutInvoiceRetrieveSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if not instance.merchant == request.user.merchant:
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance)
        signature = request.user.merchant.api_keys.get(active=True).sign_data(serializer.data)
        headers = {"Signature": signature}
        return Response(serializer.data, headers=headers)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        signature = request.user.merchant.api_keys.get(active=True).sign_data(serializer.data)

        headers = {"Signature": signature, "Content-Type": "application/json"}

        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['POST'], url_path='send-details', permission_classes=[])
    def send_details(self, request, id=None):

        if not PayOut.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'details': 'Order not found'})
        pay_out = PayOut.objects.get(id=id)

        # ip = get_client_ip(request)
        #
        # if ip != pay_out.order.client_ip and pay_out.order.client_ip != '127.0.0.1':
        #     return Response(status=status.HTTP_403_FORBIDDEN, data={'details': 'The IP has changed!'})

        try:
            with transaction.atomic():
                out_order = OutOrder.create(amount=pay_out.amount,
                                            payment_system=pay_out.payment_system, merchant=pay_out.merchant,
                                            merchant_order_id=pay_out.merchant_order_id,
                                            details=request.data, client_ip=get_client_ip(request))
                pay_out.details = request.data
        except ValidationError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)

        pay_out.order = out_order
        pay_out.save()

        if out_order.status.name == 'Cannot process':
            try:
                with transaction.atomic():
                    pay_out.failed()
            except ValidationError as e:
                return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)
            except:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            return Response(status=status.HTTP_200_OK)
        else:
            try:
                with transaction.atomic():
                    transaction_type = TransactionType.objects.get(name="Freeze")
                    Transaction.create(_from=out_order.merchant.balance, _to=out_order.trader.frozen_balance_usdt,
                                       value=out_order.usd_amount, _transaction_type=transaction_type,
                                       _linked_out_order=out_order,
                                       _comment="New out-order received")
                    pay_out.in_progress()
            except ValidationError as e:
                return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)
            except:
                return Response(status=status.HTTP_400_BAD_REQUEST)
            return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=['GET'], url_path='obtain', permission_classes=[])
    def obtain(self, request, id=None):

        if not PayOut.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'details': 'Order not found'})
        pay_out = PayOut.objects.get(id=id)

        ip = get_client_ip(request)

        if pay_out.status.name != 'New' and pay_out.status.name != 'Failed' and ip != pay_out.order.client_ip and pay_out.order.client_ip != '127.0.0.1':
            return Response(status=status.HTTP_403_FORBIDDEN, data={'details': 'ip_has_changed'})

        if pay_out.status.name == 'New':
            serializer = PayOutInvoiceNewSerializer(pay_out)
        elif pay_out.status.name == 'In Progress':
            serializer = PayOutInvoiceInProgressSerializer(pay_out)
        elif pay_out.status.name == 'Failed':
            serializer = PayOutInvoiceFailSerializer(pay_out)
        else:
            serializer = PayOutInvoiceSuccessSerializer(pay_out)
        # serializer.is_valid(raise_exception=True)
        serializer_data = serializer.data
        return Response(status=status.HTTP_200_OK, data=serializer_data)

    @action(detail=True, methods=['POST'], url_path='complete', permission_classes=[])
    def complete(self, request, id=None):

        if not PayOut.objects.filter(id=id).exists():
            return Response(status=status.HTTP_404_NOT_FOUND, data={'details': 'Order not found'})
        pay_out = PayOut.objects.select_related('order').get(id=id)

        ip = get_client_ip(request)

        if ip != pay_out.order.client_ip and pay_out.order.client_ip != '127.0.0.1':
            return Response(status=status.HTTP_403_FORBIDDEN, data={'details': 'ip_has_changed'})

        try:
            with transaction.atomic():
                order = OutOrder.objects.select_for_update().get(id=pay_out.order_id)
                if order.status.name == "Completed":
                    return Response(status=status.HTTP_200_OK, data={'success_url': pay_out.success_url})
                order.complete_after_money_sent()
        except ValidationError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data=e.detail)

        return Response(status=status.HTTP_200_OK, data={'success_url': pay_out.success_url})


class PayOutPaymentViewset(viewsets.ModelViewSet):
    lookup_field = 'id'
    permission_classes = [MerchantPermission | IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    ordering = ['id']
    http_method_names = ['post', 'get']
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'merchant'):
            merchant = user.merchant
            return PayOut.objects.filter(merchant=merchant)
        if user.is_superuser:
            return PayOut.objects.all()
        return PayOut.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return PayOutPaymentCreateSerializer
        if self.action == 'retrieve' or self.action == 'list':
            return PayOutPaymentRetrieveSerializer
        return PayOutPaymentRetrieveSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        signature = request.user.merchant.api_keys.get(active=True).sign_data(serializer.data)

        headers = {"Signature": signature, "Content-Type": "application/json"}

        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if not instance.merchant == request.user.merchant:
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance)
        signature = request.user.merchant.api_keys.get(active=True).sign_data(serializer.data)
        headers = {"Signature": signature}
        return Response(serializer.data, headers=headers)

    # @action(detail=True, methods=['POST'], url_path='complete', permission_classes=[MerchantPermission])
    # def complete(self, request, id=None):
    #
    #     if not PayOut.objects.filter(id=id).exists():
    #         return Response(status=status.HTTP_404_NOT_FOUND, data={'details': 'Order not found'})
    #     pay_out = PayOut.objects.get(id=id)
    #
    #     if not pay_out.merchant == request.user.merchant:
    #         return Response(status=status.HTTP_403_FORBIDDEN)
    #
    #     try:
    #         with transaction.atomic():
    #             pay_out.order.complete_after_money_sent()
    #     except ValidationError as e:
    #         return Response(status=status.HTTP_400_BAD_REQUEST, data=e.error_dict)
    #
    #     return Response(status=status.HTTP_200_OK, data={'success': True})


