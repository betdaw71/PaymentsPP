import logging
import os
from django.http import HttpResponseForbidden
from rest_framework.authtoken.models import Token
import hashlib
import json
from .models import APIKeys

client_gate = os.getenv('CLIENT_GATE')
platform_gate = os.getenv('PLATFORM_GATE')


class ProxyVerificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if '/mhbncejicnc3iom3c3/admin/' in request.path:
            return self.get_response(request)

        has_token = False
        token_key = request.headers.get('Authorization')
        if token_key and 'Token' in token_key:
            token_key = token_key.split(' ')[1]
            try:
                token = Token.objects.get(key=token_key)
                has_token = True
            except Token.DoesNotExist:
                has_token = False
        else:
            has_token = False

        gate_header = request.headers.get('GATE')
        gated_right = False
        if ('/api/v1/payments/in/invoice/' in request.path) or ('/api/v1/payments/out/invoice/' in request.path):
            if gate_header and gate_header == client_gate:
                gated_right = True
        else:
            if gate_header and gate_header == platform_gate:
                gated_right = True

        if gated_right or has_token:
            return self.get_response(request)
        else:
            return HttpResponseForbidden("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


class SignatureVerificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if ((('/api/v1/payments/in/invoice/' in request.path) or ('/api/v1/payments/out/invoice/' in request.path)) and 'obtain' not in request.path and 'send-details' not in request.path and 'sent' not in request.path and '/api/v1/bot/' not in request.path and 'process-sms' not in request.path and 'complete' not in request.path) or ('/api/v1/payments/in/h2h/' in request.path) or ('/api/v1/payments/out/h2h/' in request.path):
            token_key = request.headers.get('Authorization')
            if token_key and 'Token' in token_key:
                token_key = token_key.split(' ')[1]
            else:
                return HttpResponseForbidden("Invalid Token")
            if request.method != 'GET' and bool(request.body) and ('/api/v1/sms/' not in request.path):
                signature = request.headers.get('Signature')
                if not signature:
                    return HttpResponseForbidden("Signature required")
                try:
                    token = Token.objects.get(key=token_key)
                    api_key_instance = APIKeys.objects.get(merchant=token.user.merchant, active=True)
                except (Token.DoesNotExist, APIKeys.DoesNotExist):
                    return HttpResponseForbidden("Invalid Token or API Key")

                user_ip = request.META['REMOTE_ADDR']
                if api_key_instance.whitelist_on and user_ip not in api_key_instance.whitelist_ips:
                    return HttpResponseForbidden("This IP is not in whitelist")

                sorted_data = json.dumps(json.loads(request.body), sort_keys=True, separators=(',', ':')).encode()
                expected_signature = hashlib.sha256(sorted_data + str(api_key_instance.private_key).encode()).hexdigest()

                if expected_signature != signature:
                    return HttpResponseForbidden("Invalid signature")

        return self.get_response(request)
