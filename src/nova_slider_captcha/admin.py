"""Explicit opt-in Admin site; importing this module changes no existing site."""
from django.contrib.admin import AdminSite
from .forms import SliderAdminAuthenticationForm


class SliderCaptchaAdminSite(AdminSite):
    login_form = SliderAdminAuthenticationForm
    login_template = "nova_slider_captcha/admin_login.html"
