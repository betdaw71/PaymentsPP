from django.contrib import admin

from payments.integrations.melbet.models import MelbetIntegrationConfig, MelbetTransactionSession


@admin.register(MelbetIntegrationConfig)
class MelbetIntegrationConfigAdmin(admin.ModelAdmin):
    list_display = ("merchant", "public_key", "active", "whitelist_on", "created_at")
    search_fields = ("merchant__user__username", "public_key")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MelbetTransactionSession)
class MelbetTransactionSessionAdmin(admin.ModelAdmin):
    list_display = ("order_id", "config", "pay_in", "pay_out", "melbet_method", "created_at")
    search_fields = ("order_id",)
    readonly_fields = ("created_at",)
