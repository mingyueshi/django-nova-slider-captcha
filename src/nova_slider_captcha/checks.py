from django.conf import settings
from django.core.checks import Error, Tags, register

from .conf import challenge_policy, configured_alternative_link, purposes, rate_limit, rate_log_level


@register(Tags.security)
def captcha_settings_check(app_configs, **kwargs):
    errors = []
    middleware = getattr(settings, "MIDDLEWARE", [])
    for name, identifier in (("django.contrib.sessions.middleware.SessionMiddleware", "nova_slider_captcha.E001"), ("django.middleware.csrf.CsrfViewMiddleware", "nova_slider_captcha.E002")):
        if name not in middleware:
            errors.append(Error(f"Nova Slider CAPTCHA requires {name}.", id=identifier))
    try:
        for action in ("issue", "verify"):
            for scope in ("session", "ip"):
                rate_limit(action, scope)
    except (ValueError, TypeError, AttributeError) as error:
        errors.append(Error(str(error), id="nova_slider_captcha.E003"))
    for validator, identifier in ((purposes, "nova_slider_captcha.E004"), (rate_log_level, "nova_slider_captcha.E005"), (challenge_policy, "nova_slider_captcha.E006")):
        try:
            validator()
        except ValueError as error:
            errors.append(Error(str(error), id=identifier))
    try:
        configured_alternative_link()
    except ValueError as error:
        errors.append(Error(str(error), id="nova_slider_captcha.E007"))
    return errors
