from django.urls import path

from . import views

app_name = "chatbot"

urlpatterns = [
    path("", views.chat_index, name="index"),
    path("messages/", views.send_message, name="send_message"),
]
