"""Explicit opt-in Admin site; importing this module changes no existing site."""
from django.contrib.admin import AdminSite
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed
from django.template.response import TemplateResponse
from django.urls import path, reverse, reverse_lazy
from django.utils.translation import gettext as _

from .forms import SliderAdminAuthenticationForm
from .rate_stats import rate_stats

_RATE_STATS_PERMISSIONS = (
    "nova_slider_captcha.view_ratelimitstate",
    "nova_slider_captcha.view_ratebucket",
)


def _rate_stats_navigation(url):
    """Read-only navigation for templates that render the Django app list."""
    return [{
        "name": _("CAPTCHA rate statistics"),
        "app_label": "nova-slider-operations",
        "app_url": url,
        "has_module_perms": True,
        "models": [{
            "name": _("View CAPTCHA rate statistics"),
            "object_name": "RateStatistics",
            "admin_url": url,
            "view_only": True,
            "perms": {"view": True},
        }],
    }]


class SliderCaptchaAdminSite(AdminSite):
    login_form = SliderAdminAuthenticationForm
    login_template = "nova_slider_captcha/admin_login.html"
    index_template = "nova_slider_captcha/admin_index.html"

    def _can_view_rate_stats(self, request):
        user = request.user
        return (
            user.is_active and user.is_staff and self.has_permission(request)
            and user.has_perms(_RATE_STATS_PERMISSIONS)
        )

    def index(self, request, extra_context=None):
        context = dict(extra_context or {})
        url = (
            reverse("admin:nova_slider_rate_stats", current_app=self.name)
            if self._can_view_rate_stats(request) else None
        )
        context["nova_rate_stats_url"] = url
        # Navigation for a statistics-only index, scoped to the template's
        # parent content block. Leave the registry and actual app list alone.
        if url:
            context["nova_rate_stats_navigation"] = _rate_stats_navigation(url)
        return super().index(request, extra_context=context)

    def get_urls(self):
        view = self.admin_view(self.rate_stats_view)
        view.admin_site = self
        view.login_url = reverse_lazy("admin:login", current_app=self.name)
        return [path("nova-slider/rate-stats/", view, name="nova_slider_rate_stats"), *super().get_urls()]

    def rate_stats_view(self, request):
        if not self._can_view_rate_stats(request):
            raise PermissionDenied
        if request.method not in ("GET", "HEAD"):
            return HttpResponseNotAllowed(["GET", "HEAD"])
        request.current_app = self.name
        return TemplateResponse(request, "nova_slider_captcha/admin_rate_stats.html", {
            **self.each_context(request),
            "title": _("CAPTCHA rate statistics"),
            "nova_rate_stats_navigation": _rate_stats_navigation(request.path),
            "stats": rate_stats(),
        })
