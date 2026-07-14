from django.urls import path

from payments.integrations.melbet.views import (
    MelbetDepositView,
    MelbetTransactionStatusView,
    MelbetWithdrawalView,
)

app_name = "melbet"

urlpatterns = [
    path("deposit/", MelbetDepositView.as_view(), name="deposit"),
    path("withdrawal/", MelbetWithdrawalView.as_view(), name="withdrawal"),
    path("transactions/<uuid:transaction_id>/", MelbetTransactionStatusView.as_view(), name="status"),
]
