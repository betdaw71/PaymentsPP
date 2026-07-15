from django.urls import include, path
from rest_framework import routers
from basics import viewsets

from basics import views
app_name = 'basics'
router = routers.DefaultRouter()
router.register(r'language', viewsets.LanguageViewSet, basename="Language")
router.register(r'currency', viewsets.CurrencyViewSet, basename="Currency")
router.register(r'payment-system', viewsets.PaymentSystemViewSet, basename="PaymentSystem")
router.register(r'details', viewsets.PaymentDetailsGroupViewSet, basename="PaymentDetailsGroup")
router.register(r'trader-team', viewsets.TraderTeamViewset, basename="TraderTeam")
router.register(r'trader', viewsets.TraderViewSet, basename="Trader")
router.register(r'balance', viewsets.BalanceViewset, basename="Balance")
router.register(r'support-member', viewsets.SupportMemberViewSet, basename="SupportMember")
router.register(r'teamlead', viewsets.TeamLeadViewset, basename="TeamLead")
router.register(r'traffic-type', viewsets.TrafficTypeViewset, basename="TrafficType")


urlpatterns = [
    path(r'transfer-targets/', views.get_transfer_targets),
    path(r'trading-team/trader/', views.get_trading_team_trader),
    path(r'trading-team/support/', views.get_trading_team_support),
    path(r'balance-targets/support/', views.get_balance_filter_support),
    path(r'balance-targets/trader/', views.get_balance_filter_trader),
    path(r'withdrawal-targets/', views.get_user_filter_support),
    path(r'update-balances/', views.update_balances),
    path(r'get-balances/', views.get_balances_stats),
    path(r'pdgroup-creation-data/', views.get_pdgroup_creation_data),
    path(r'pd-creation-data/', views.get_pd_creation_data),
    path(r'get-filters-pd/', views.get_filters_payment_details),
    path(r'exchange-rates/', views.get_exchange_rates),
    path(r'dashboard/', views.get_dashboard),
    path(r'autoclose-off/', views.autoclose_off),
    path(r'autoclose-on/', views.autoclose_on),
    path('', include(router.urls)),
]
