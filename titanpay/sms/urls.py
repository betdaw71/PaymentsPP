from django.urls import include, path
from rest_framework import routers
from sms import views
from django.urls import include, path
from rest_framework import routers
from sms import viewsets

app_name = 'sms'
router = routers.DefaultRouter()
router.register(r'sms', viewsets.SMSViewSet, basename="SMS")

urlpatterns = [
    path(r'get-filters/', views.get_filters_sms),
    path(r'blocks/', views.get_blocks),
    path(r'process-sms/', views.process_sms),
    path(r'liveness/', views.liveness),
    path('', include(router.urls)),
]

