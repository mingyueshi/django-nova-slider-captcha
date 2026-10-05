from django.conf import settings

WIDTH = 320
HEIGHT = 160
PIECE_SIZE = 44
CHALLENGE_TTL = 120
TOKEN_TTL = 60
MAX_ATTEMPTS = 5
TOLERANCE = 4
PURPOSES = frozenset(("demo", "login"))


def rate_limit(action, scope):
    defaults = {"issue_session": 20, "issue_ip": 60, "verify_session": 60, "verify_ip": 120}
    key = f"{action}_{scope}"
    value = getattr(settings, "NOVA_SLIDER_RATE_LIMITS", {}).get(key, defaults[key])
    if type(value) is not int or value < 1:
        raise ValueError(f"NOVA_SLIDER_RATE_LIMITS[{key!r}] must be a positive integer")
    return value
