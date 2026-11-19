from django.contrib.auth.models import Group, User
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.urls import include, path
from nova_slider_captcha.admin import SliderCaptchaAdminSite

from . import profile

admin_site = SliderCaptchaAdminSite(name="admin")
admin_site.register(User, UserAdmin)
admin_site.register(Group, GroupAdmin)
urlpatterns = [
    path("captcha/", include("nova_slider_captcha.urls")),
    path("captcha-demo/", include("nova_slider_captcha.demo_urls")),
    path("admin/", admin_site.urls),
    path("profile-demo/login/", profile.DemoLoginView.as_view(), name="demo-profile-login"),
    path("profile-demo/", profile.change_name, name="demo-profile"),
    path("profile-demo/alternative/", profile.change_name, {"alternative": True}, name="demo-profile-alternative"),
]
