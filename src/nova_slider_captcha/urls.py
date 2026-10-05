from django.urls import path
from . import views

app_name = "nova_slider_captcha"
urlpatterns = [
    path("", views.demo, name="demo"),
    path("init", views.init, name="init"),
    path("challenge", views.challenge, name="challenge"),
    path("verify", views.verify, name="verify"),
    path("submit", views.submit, name="submit"),
    path("demo", views.submit, name="protected-demo"),
]
