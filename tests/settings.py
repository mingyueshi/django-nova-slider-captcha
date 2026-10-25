from demo.settings import *
# Checks and migration-drift checks must also avoid the example database.
DATABASES["default"]["NAME"] = DATABASES["default"]["TEST"]["NAME"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
