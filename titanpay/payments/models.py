import logging
from decimal import Decimal

from django.db import models
from basics.models import Currency, PaymentSystem
from trade.models import InOrder, OutOrder
from merchant.models import Merchant
import json
import hashlib
import requests
from django.utils import timezone
import uuid
from django.core.validators import MinValueValidator
from payments.utils import UUIDEncoder


class PayInStatus(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name


class APIKeys(models.Model):
    merchant = models.ForeignKey(to=Merchant, on_delete=models.SET_NULL, null=True, related_name="api_keys")
    private_key = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    whitelist_on = models.BooleanField(default=False)
    whitelist_ips = models.JSONField(default=list())
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    @classmethod
    def create(cls, merchant: Merchant):
        current_keys = cls.objects.filter(merchant=merchant, active=True)
        for key in current_keys:
            key.active = False
            key.save()
        obj = cls(merchant=merchant)
        obj.save()
        return obj

    def sign_data(self, data):
        sorted_data = json.dumps(data, sort_keys=True, separators=(',', ':'), cls=UUIDEncoder).encode()
        signature = hashlib.sha256(sorted_data + str(self.private_key).encode()).hexdigest()
        return signature

    def update_whitelist(self, whitelist_on, whitelist):
        self.whitelist_ips = whitelist
        self.whitelist_on = whitelist_on
        self.save()


class Device(models.Model):
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=255)
    is_blacklisted = models.BooleanField(default=False)


class Client(models.Model):
    merchant = models.ForeignKey(to=Merchant, on_delete=models.SET_NULL, null=True)
    client_id = models.CharField(max_length=255)
    order_count = models.IntegerField(default=0)
    success_order_count = models.IntegerField(default=0)
    email = models.CharField(max_length=63, null=True, blank=True)
    phone = models.CharField(max_length=31, null=True, blank=True)
    name = models.CharField(max_length=63, null=True, blank=True)
    devices = models.ManyToManyField(to=Device, null=True, blank=True)
    is_blacklisted = models.BooleanField(default=False)


class PayIn(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    amount = models.DecimalField(validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    currency = models.ForeignKey(to=Currency, on_delete=models.SET_NULL, null=True)
    payment_system = models.ForeignKey(to=PaymentSystem, on_delete=models.SET_NULL, null=True)
    merchant_order_id = models.CharField(max_length=255, unique=True)  # Order ID in Merchant's system
    success_url = models.URLField(null=True, blank=True)
    failed_url = models.URLField(null=True, blank=True)
    pending_url = models.URLField(null=True, blank=True)
    callback_url = models.URLField()
    recalculated = models.BooleanField(default=False)
    status = models.ForeignKey(to=PayInStatus, on_delete=models.SET_NULL, null=True)
    client = models.ForeignKey(to=Client, on_delete=models.SET_NULL, null=True)
    merchant = models.ForeignKey(to=Merchant, on_delete=models.SET_NULL, null=True)
    order = models.ForeignKey(to=InOrder, on_delete=models.SET_NULL, null=True, related_name="pay_in")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=True)

    def send_callback(self, data):
        if self.callback_url is None or self.callback_url == "":
            return
        from payments.integrations.melbet.callbacks import try_send_melbet_payin_callback

        status_name = data.get("status") if isinstance(data, dict) else None
        if try_send_melbet_payin_callback(self, status_name=status_name):
            return
        data["id"] = str(self.id)
        data["order_id"] = self.merchant_order_id
        data["amount"] = float(self.amount)
        data["currency"] = self.currency.symbol
        data["payment_system"] = self.payment_system.name
        data["recalculated"] = self.order.recalculated
        data["timestamp"] = int(timezone.now().timestamp())
        signature = self.merchant.api_keys.get(active=True).sign_data(data)

        headers = {"Signature": signature, "Content-Type": "application/json"}

        status_code = 500
        response_text = ""
        try:
            r = requests.post(self.callback_url, json=data, headers=headers)
            status_code = r.status_code
            response_text = (r.text or "")[:2000]
        except Exception as exc:
            logging.error(f"Callback to {self.callback_url} failed: {exc}")
            response_text = str(exc)

        from payments.payin_trace import Direction, trace_log

        trace_log(
            pay_in=self,
            direction=Direction.MERCHANT_CALLBACK,
            body={"request": data, "response_preview": response_text},
            http_method="POST",
            url=self.callback_url,
            status_code=status_code,
            note=f"status={data.get('status')}",
        )

        return status_code

    def change_status(self, status_name, *, send_callback: bool = True):
        new_status = PayInStatus.objects.get(name=status_name)
        self.status = new_status
        self.updated_at = timezone.now()
        self.save()
        if send_callback:
            self.send_callback({"status": status_name})

    def recalculate(self, new_amount):
        self.amount = new_amount
        self.save()
        data = {"status": self.status.name}
        self.send_callback(data)

    def in_progress(self):
        self.change_status("In Progress")

    def failed(self):
        self.change_status("Failed")

    def declined(self, *, send_callback: bool = True):
        self.change_status("Declined", send_callback=send_callback)

    def success(self):
        self.change_status("Success")


class FairpayPayInSession(models.Model):
    """Связка PayIn ↔ заявка FairPay (provider id, ответ create, последний webhook)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="fairpay_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_order_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_status = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ExpayonePayInSession(models.Model):
    """Связка PayIn ↔ сделка ExpayOne H2H (order_id UUID, ответ create, webhook)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="expayone_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_order_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_status = models.CharField(max_length=64, blank=True, default="")
    last_notified_sub_status = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ProtocolPayInSession(models.Model):
    """Связка PayIn ↔ платёж Protocol (prot0col.com API v2)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="protocol_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_payment_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_state = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class GipayPayInSession(models.Model):
    """Связка PayIn ↔ платёж GiPay (gipay.org API v2, Aggrepay)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="gipay_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_payment_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_state = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class VisionxPayInSession(models.Model):
    """Связка PayIn ↔ инвойс VisionX Pay (POST /api/merchant/invoices, H2H Scenario A)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="visionx_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_invoice_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    provider_deal_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    notification_token = models.CharField(max_length=128, blank=True, default="")
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_state = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PayplatPayInSession(models.Model):
    """Связка PayIn ↔ сделка PayPlat (POST /v1/api/deals)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="payplat_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_order_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_state = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BitzonePayInSession(models.Model):
    """Связка PayIn ↔ сделка Bitzone (POST /payment/trading/pay-in)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="bitzone_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_transaction_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_status = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SyndicatePayInSession(models.Model):
    """Связка PayIn ↔ ордер Syndicate Pay (POST /api/orders/create)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="syndicate_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_order_id = models.CharField(max_length=32, blank=True, default="", db_index=True)
    payment_system_name = models.CharField(max_length=64, blank=True, default="")
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_status = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BotonpayPayInSession(models.Model):
    """Связка PayIn ↔ сделка BotonPay (POST /api/public/v1/deals)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="botonpay_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_deal_uuid = models.CharField(max_length=64, blank=True, default="", db_index=True)
    payment_system_name = models.CharField(max_length=64, blank=True, default="")
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_status = models.CharField(max_length=64, blank=True, default="")
    last_status_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PlutusPayInSession(models.Model):
    """Связка PayIn ↔ сделка PlutusPay (POST /merchant/v2/incoming/payment/create/)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="plutus_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_trade_uuid = models.CharField(max_length=64, blank=True, default="", db_index=True)
    payment_system_name = models.CharField(max_length=64, blank=True, default="")
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_status = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ConcoredPayInSession(models.Model):
    """Связка PayIn ↔ платёж Concored / ProcessorCore (MMK KBZPay, WavePay)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="concored_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_payment_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    payment_system_name = models.CharField(max_length=64, blank=True, default="")
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_status = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PaymapPayInSession(models.Model):
    """Связка PayIn ↔ PayMap (API v2 fiat invoice, KZT)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="paymap_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_invoice_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    payment_system_name = models.CharField(max_length=64, blank=True, default="")
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_status = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PlaymentsPayInSession(models.Model):
    """Связка PayIn ↔ депозит Playments (TRY bank transfer H2H)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.OneToOneField(to="PayIn", on_delete=models.CASCADE, related_name="playments_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_deposit_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_status = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PlaymentsPayOutSession(models.Model):
    """Связка PayOut ↔ вывод Playments (TRY bank transfer)."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_out = models.OneToOneField(to="PayOut", on_delete=models.CASCADE, related_name="playments_session")
    external_id = models.CharField(max_length=128, db_index=True)
    provider_withdrawal_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    create_response = models.JSONField(default=dict, blank=True)
    last_webhook_payload = models.JSONField(default=dict, blank=True)
    last_notified_status = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PayInTraceLog(models.Model):
    """Audit-trail тел HTTP для pay-in: мерчант, Protocol, колбеки."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    pay_in = models.ForeignKey(
        to="PayIn",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="trace_logs",
    )
    merchant = models.ForeignKey(to=Merchant, on_delete=models.SET_NULL, null=True, blank=True)
    merchant_order_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    direction = models.CharField(max_length=32, db_index=True)
    http_method = models.CharField(max_length=16, blank=True, default="")
    url = models.CharField(max_length=512, blank=True, default="")
    status_code = models.IntegerField(null=True, blank=True)
    body = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["direction", "created_at"]),
            models.Index(fields=["merchant_order_id", "created_at"]),
        ]


class PayOutStatus(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name


class PayOut(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    amount = models.DecimalField(validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    currency = models.ForeignKey(to=Currency, on_delete=models.SET_NULL, null=True)
    payment_system = models.ForeignKey(to=PaymentSystem, on_delete=models.SET_NULL, null=True)
    details = models.JSONField(null=True)
    merchant_order_id = models.CharField(max_length=255)  # Order ID in Merchant's system
    success_url = models.URLField(null=True, blank=True)
    failed_url = models.URLField(null=True, blank=True)
    callback_url = models.URLField()
    status = models.ForeignKey(to=PayOutStatus, on_delete=models.SET_NULL, null=True)

    client = models.ForeignKey(to=Client, on_delete=models.SET_NULL, null=True)
    merchant = models.ForeignKey(to=Merchant, on_delete=models.SET_NULL, null=True)
    order = models.ForeignKey(to=OutOrder, on_delete=models.SET_NULL, null=True, related_name="pay_out")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=True)

    def send_callback(self, data):
        if self.callback_url is None or self.callback_url == "":
            return

        from payments.integrations.melbet.callbacks import try_send_melbet_payout_callback

        status_name = data.get("status") if isinstance(data, dict) else None
        if try_send_melbet_payout_callback(self, status_name=status_name):
            return

        data["id"] = str(self.id)
        data["order_id"] = self.merchant_order_id
        data["amount"] = float(self.amount)
        data["currency"] = self.currency.symbol
        data["payment_system"] = self.payment_system.name
        data["recalculated"] = self.order.recalculated
        data["timestamp"] = int(timezone.now().timestamp())
        signature = self.merchant.api_keys.get(active=True).sign_data(data)

        headers = {"Signature": signature, "Content-Type": "application/json"}

        status_code = 500
        try:
            r = requests.post(self.callback_url, json=data, headers=headers)
            status_code = r.status_code
        except Exception:
            logging.error(f"Callback to {self.callback_url} failed")

        return status_code

    def change_status(self, status_name):
        new_status = PayOutStatus.objects.get(name=status_name)
        self.status = new_status
        self.updated_at = timezone.now()
        self.save()
        self.send_callback({"status": status_name})

    def recalculate(self, new_amount: Decimal):
        self.amount = new_amount
        self.save()
        data = {"status": self.status.name}
        self.send_callback(data)

    def in_progress(self):
        self.change_status("In Progress")

    def failed(self):
        self.change_status("Failed")

    def declined(self):
        self.change_status("Declined")

    def success(self):
        self.change_status("Success")
