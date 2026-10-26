from django.urls import path
from . import views

app_name = "nova_slider_captcha"
urlpatterns = [
    path("", views.api_root, name="api-root"),
    path("init", views.init, name="init"),
    path("challenge", views.challenge, name="challenge"),
    path("verify", views.verify, name="verify"),
]
