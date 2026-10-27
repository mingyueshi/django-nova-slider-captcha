"""Fresh-process session capability probe, also serving as a custom backend."""
from django.contrib.sessions.backends.signed_cookies import SessionStore as SessionStore


def main():
    import json
    from pathlib import Path
    import sys
    from tempfile import TemporaryDirectory

    from django.conf import settings
    with TemporaryDirectory(prefix="nova-session-backend-") as tmp:
        backend = sys.argv[1]
        settings.configure(
            SECRET_KEY="isolated-test-only", ALLOWED_HOSTS=["testserver"],
            INSTALLED_APPS=["nova_slider_captcha"], ROOT_URLCONF="nova_slider_captcha.urls",
            MIDDLEWARE=["django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.csrf.CsrfViewMiddleware"],
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(Path(tmp) / "test.sqlite3")}},
            SESSION_ENGINE="tests.session_backend_probe" if backend == "custom" else "django.contrib.sessions.backends." + backend,
            SESSION_FILE_PATH=tmp, USE_TZ=True,
        )
        import django
        django.setup()
        from django.core.management import call_command
        from django.test import Client, RequestFactory
        from nova_slider_captcha import services
        from nova_slider_captcha.checks import captcha_settings_check
        if backend not in ("db", "cached_db"):
            call_command("migrate", verbosity=0)
        client = Client(enforce_csrf_checks=True)
        response = client.get("/init")
        # Public JSON wrapper must also fail closed for the invalid backend.
        post = client.post("/challenge", '{"purpose":"demo"}', content_type="application/json", HTTP_X_CSRFTOKEN=response.json().get("csrfToken", "")) if response.status_code == 200 else Client().post("/challenge", '{"purpose":"demo"}', content_type="application/json")
        req = RequestFactory().get("/")
        req.session = {}
        rejected = False
        try:
            services.issue(req, "demo")
        except ValueError:
            rejected = True
        print(json.dumps({"checks": [e.id for e in captcha_settings_check(None)], "status": response.status_code,
                          "challenge_status": post.status_code, "issue_rejected": rejected}))


if __name__ == "__main__":
    main()
