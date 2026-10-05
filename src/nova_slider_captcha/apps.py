from django.apps import AppConfig


class NovaSliderCaptchaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nova_slider_captcha"
    verbose_name = "Nova Slider CAPTCHA"

    def ready(self):
        from . import checks  # noqa: F401
