from django.contrib import admin

from appeals.models import AppealCounterparty, AppealTelegramChat, PayInAppeal


@admin.register(AppealCounterparty)
class AppealCounterpartyAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "merchant", "psp_provider", "trader_username", "is_active", "id")
    list_filter = ("role", "is_active", "psp_provider")
    search_fields = ("name", "id", "psp_provider")
    readonly_fields = ("id", "created_at")


@admin.register(AppealTelegramChat)
class AppealTelegramChatAdmin(admin.ModelAdmin):
    list_display = ("title", "telegram_chat_id", "counterparty", "is_active", "updated_at")
    list_filter = ("is_active", "counterparty__role")
    search_fields = ("title", "telegram_chat_id")


@admin.register(PayInAppeal)
class PayInAppealAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "pay_in",
        "status",
        "psp_provider",
        "provider_external_id",
        "source",
        "merchant_inline_clicked",
        "created_at",
    )
    list_filter = ("status", "source", "psp_provider", "merchant_inline_clicked")
    search_fields = ("id", "pay_in__id", "provider_external_id")
    readonly_fields = ("id", "created_at")
