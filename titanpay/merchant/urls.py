from django.urls import include, path
from rest_framework import routers
from merchant import viewsets
from merchant import views
app_name = 'merchant'
router = routers.DefaultRouter()
router.register(r'merchant', viewsets.MerchantViewSet, basename="Merchant")
router.register(r'merchant-fees', viewsets.MerchantSolutionViewset, basename="MerchantFees")

urlpatterns = [
    path(r'get-fees/', views.get_solutions),
    path('', include(router.urls)),
]
