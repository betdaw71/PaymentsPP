from rest_framework.permissions import BasePermission, IsAuthenticated, SAFE_METHODS
from titanpay import settings


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS or request.user.is_superuser and request.user.is_authenticated:
            return True
        return False


class SupportPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'supportmember'):
            return True
        return False


class HeadSupportPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'supportmember'):
            if request.user.supportmember.is_head:
                return True
        return False


class TraderPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'trader'):
            return True
        return False


class TraderDevicePermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'traderdevice'):
            return True
        return False


class TgBotPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'tgbot'):
            return True
        return False


class MerchantPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'merchant'):
            return True
        return False


class TeamLeadPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'teamlead'):
            return True
        return False


class DebugPermission(BasePermission):
    def has_permission(self, request, view):
        if settings.DEBUG and request.user.is_authenticated:
            return True


class TraderDevicePermission(BasePermission):
    def has_permission(self, request, view):
        if hasattr(request.user, 'traderdevice'):
            return True
        return False