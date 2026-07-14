from __future__ import annotations

import secrets
import uuid

from django.db import models


class MelbetIntegrationConfig(models.Model):
    """Credentials and routing for one merchant on Melbet typical integration."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    merchant = models.OneToOneField(
        to="merchant.Merchant",
        on_delete=models.CASCADE,
        related_name="melbet_integration",
    )
    public_key = models.CharField(max_length=128, unique=True, db_index=True)
    secret_key = models.CharField(max_length=128)
    active = models.BooleanField(default=True)
    whitelist_on = models.BooleanField(default=False)
    whitelist_ips = models.JSONField(default=list, blank=True)
    method_map = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'JSON map melbet "method" -> {"payment_system": "C2C", "currency": "RUB"}. '
            'Use key "default" as fallback.'
        ),
    )
    default_ftd = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "payments"
        verbose_name = "Melbet integration"
        verbose_name_plural = "Melbet integrations"

    def __str__(self) -> str:
        user = getattr(self.merchant, "user", None)
        name = getattr(user, "username", self.merchant_id)
        return f"Melbet:{name}"

    @classmethod
    def generate_keys(cls) -> tuple[str, str]:
        public_key = secrets.token_urlsafe(32)
        secret_key = secrets.token_hex(32)
        return public_key, secret_key


class MelbetTransactionSession(models.Model):
    """Links Melbet order_id / method / account_number to internal PayIn or PayOut."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    config = models.ForeignKey(
        MelbetIntegrationConfig,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    pay_in = models.OneToOneField(
        to="payments.PayIn",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="melbet_session",
    )
    pay_out = models.OneToOneField(
        to="payments.PayOut",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="melbet_session",
    )
    order_id = models.CharField(max_length=255, db_index=True)
    melbet_method = models.CharField(max_length=64, blank=True, default="")
    account_number = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "payments"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(pay_in__isnull=False, pay_out__isnull=True)
                    | models.Q(pay_in__isnull=True, pay_out__isnull=False)
                ),
                name="melbet_session_payin_xor_payout",
            ),
            models.UniqueConstraint(fields=["config", "order_id"], name="melbet_session_config_order_id"),
        ]
