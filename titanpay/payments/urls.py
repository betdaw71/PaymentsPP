from django.urls import include, path
from rest_framework import routers
from payments import viewsets
app_name = 'payments'
router = routers.DefaultRouter()
router.register(r'in/invoice', viewsets.PayInInvoiceViewset, basename="PayIn-Invoice")
router.register(r'currencies', viewsets.CurrenciesViewset, basename="Currencies")
router.register(r'payment-systems', viewsets.PaymentSystemsViewset, basename="PaymentSystems")
router.register(r'in/h2h', viewsets.PayInPaymentViewset, basename="PayIn-H2H")
# router.register(r'out/invoice', viewsets.PayOutInvoiceViewset, basename="PayOut-Invoice")
router.register(r'out/h2h', viewsets.PayOutPaymentViewset, basename="PayOut-H2H")
router.register(r'keys', viewsets.APIKeysViewset, basename="APIKeys")

urlpatterns = router.urls