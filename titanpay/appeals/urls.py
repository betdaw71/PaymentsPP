from django.urls import path

from appeals import views

app_name = "appeals"

urlpatterns = [
    path("init_chat/", views.init_chat),
    path("chat_role/", views.chat_role),
    path("process_message/", views.process_message),
]
