"""
URL configuration for titanpay project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from payments.fairpay_views import FairpayWebhookView
from payments.expayone_views import ExpayoneWebhookView
from payments.protocol_views import ProtocolWebhookView
from payments.playments_views import PlaymentsDepositWebhookView, PlaymentsWithdrawalWebhookView
from payments.payment_page import payment_page, payment_page_redirect

admin.site.site_header = admin.site.site_title = 'AvaPay'
admin.site.index_title = 'AvaPay administration'
from drf_yasg.views import get_schema_view
from rest_framework import permissions
from drf_yasg import openapi


urlpatterns = [
    path('mhbncejicnc3iom3c3/admin/', admin.site.urls),
    path('api/v1/base/', include('basics.urls', 'basics')),
    path('api/v1/merchant/', include('merchant.urls', 'merchant')),
    path('api/v1/trade/', include('trade.urls', 'trade')),
    path('api/v1/auth/', include('usermanagement.urls')),
    path('api/v1/payments/', include('payments.urls', 'payments')),
    path('api/v1/integrations/melbet/', include('payments.integrations.melbet.urls', 'melbet')),
    path('api/v1/bot/', include('bots.urls', 'bots')),
    path('api/v1/sms/', include('sms.urls', 'sms')),
    path('api/v1/webhooks/psp/fairpay/', FairpayWebhookView.as_view(), name='webhook-fairpay'),
    path('api/v1/webhooks/psp/expayone/', ExpayoneWebhookView.as_view(), name='webhook-expayone'),
    path('api/v1/webhooks/psp/protocol/', ProtocolWebhookView.as_view(), name='webhook-protocol'),
    path('api/v1/webhooks/psp/playments/deposit/', PlaymentsDepositWebhookView.as_view(), name='webhook-playments-deposit'),
    path('api/v1/webhooks/psp/playments/withdrawal/', PlaymentsWithdrawalWebhookView.as_view(), name='webhook-playments-withdrawal'),
    path('prometheus-X60iSjSJB4PA2mdqDnA1mRBZbmGpapdMpwZ6L29c', include('django_prometheus.urls')),
    # Платёжная страница (invoice / redirect): pay.{domain}/{uuid}
    path('<uuid:pay_in_id>/', payment_page, name='payment-page'),
    path('<uuid:pay_in_id>/redirect/', payment_page_redirect, name='payment-page-redirect'),
    # path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    # path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
