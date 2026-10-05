from django.contrib.auth.models import Group, User
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.urls import include, path
from nova_slider_captcha.admin import SliderCaptchaAdminSite

admin_site = SliderCaptchaAdminSite(name="admin")
admin_site.register(User, UserAdmin)
admin_site.register(Group, GroupAdmin)
urlpatterns = [path("captcha/", include("nova_slider_captcha.urls")), path("admin/", admin_site.urls)]
