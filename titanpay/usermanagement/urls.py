from django.urls import path, include
from usermanagement.views import MyObtainTokenPairView, RegisterMerchantView, RegisterTraderView, RegisterSupportView, \
    ChangePasswordView, get_me, TwoFactorSetupView, super_block, super_unblock, get_notifications, update_user
from rest_framework_simplejwt.views import TokenRefreshView


urlpatterns = [
    path('login/', MyObtainTokenPairView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register-support/', RegisterSupportView.as_view(), name='auth_register_support'),
    path('register-trader/', RegisterTraderView.as_view(), name='auth_register_trader'),
    path('register-merchant/', RegisterMerchantView.as_view(), name='auth_register_merchant'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('2fa-setup/', TwoFactorSetupView.as_view(), name='2fa_setup'),
    path('me/', get_me, name='get_me'),
    path('notifications/', get_notifications, name='get_me'),
    path('block/', super_block, name='super_block'),
    path('unblock/', super_unblock, name='super_unblock'),
    path('update-user/<uuid:id>/', update_user, name='update_user'),
]