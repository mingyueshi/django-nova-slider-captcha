from demo.settings import *
# Checks and migration-drift checks must also avoid the example database.
DATABASES["default"]["NAME"] = DATABASES["default"]["TEST"]["NAME"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Separate isolated stores simulate a writer and an intentionally lagged replica.
for alias in ("captcha", "replica"):
    name = str(DATABASES["default"]["NAME"]) + "." + alias
    DATABASES[alias] = {"ENGINE": "django.db.backends.sqlite3", "NAME": name, "TEST": {"NAME": name}}
