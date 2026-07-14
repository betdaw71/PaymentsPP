from __future__ import annotations

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from payments.integrations.melbet.crypto import verify_body
from payments.integrations.melbet.models import MelbetIntegrationConfig
from trade.utils import get_client_ip


class MelbetIntegrationAuthentication(BaseAuthentication):
    """x-api-key + x-signature (HMAC-SHA256 raw body). Does not use Token/SHA256 Merchant API."""

    keyword = "Melbet"

    def authenticate(self, request):
        api_key = request.headers.get("x-api-key") or request.META.get("HTTP_X_API_KEY")
        signature = request.headers.get("x-signature") or request.META.get("HTTP_X_SIGNATURE")
        if not api_key:
            raise AuthenticationFailed("x-api-key required")
        if not signature:
            raise AuthenticationFailed("x-signature required")

        try:
            config = MelbetIntegrationConfig.objects.select_related("merchant__user").get(
                public_key=api_key,
                active=True,
            )
        except MelbetIntegrationConfig.DoesNotExist as exc:
            raise AuthenticationFailed("Invalid API key") from exc

        body = b"" if request.method == "GET" else (request.body or b"")
        if not verify_body(body, signature, config.secret_key):
            raise AuthenticationFailed("Unvalid signature")

        if config.whitelist_on:
            client_ip = get_client_ip(request)
            allowed = config.whitelist_ips if isinstance(config.whitelist_ips, list) else []
            if client_ip not in allowed:
                raise AuthenticationFailed("IP not in whitelist")

        request.melbet_config = config
        return (config.merchant.user, None)
