from django.urls import include, path
from rest_framework import routers
from trade import viewsets
from trade.views import update_view, get_filters_inorder, get_filters_outorder, get_stats_orders, get_solutions

app_name = 'trade'
router = routers.DefaultRouter()
router.register(r'withdrawal-request', viewsets.WithdrawalRequestViewset, basename="WithdrawalRequest")
router.register(r'transaction', viewsets.TransactionViewset, basename="Transaction")
router.register(r'order/in', viewsets.InOrderViewset, basename="InOrder")
router.register(r'order/out', viewsets.OutOrderViewset, basename="OutOrder")
router.register(r'rates', viewsets.TraderTeamRatesViewset, basename="TraderTeamRates")


urlpatterns = [
    path(r'update/', update_view),
    path(r'stats/', get_stats_orders),
    path(r'get-filters-order/in/', get_filters_inorder),
    path(r'get-filters-order/out/', get_filters_outorder),
    path(r'get-rates/', get_solutions),
    # path(fr'order/', get_order),
    # path(fr'order/sent/', send_order),
    # path(fr'order/cancel/', close_order),
    # path(fr'order/arbitrage/', arbitrage_order),
    path('', include(router.urls)),
]
