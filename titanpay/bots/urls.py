from django.urls import include, path

from bots import views
app_name = 'bots'


urlpatterns = [
    path(r'add_pdf/', views.add_pdf),
    path(r'check_user/', views.check_user),
    path(r'reject/', views.reject),
    path(r'get_next_outorder/', views.get_next_outorder),
    path(r'get_rejection_reasons/', views.get_rejection_reasons),
    path(r'get_sms_bot_data/', views.get_sms_bot_data),
    path(r'get_sms_bot_owners/', views.get_sms_bot_owners),
    path(r'check_user_emergency/', views.check_user_emergency),
]