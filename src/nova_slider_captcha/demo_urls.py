"""Optional local demonstration; never included by the core API URLConf."""
from django.urls import path

from . import views

app_name = "nova_slider_captcha_demo"
urlpatterns = [
    path("", views.demo, name="index"),
    path("submit", views.submit, name="submit"),
    path("demo", views.submit, name="protected-demo"),
]
