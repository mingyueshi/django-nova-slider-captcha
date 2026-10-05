from django.conf import settings

WIDTH = 320
HEIGHT = 160
PIECE_SIZE = 44
CHALLENGE_TTL = 120
TOKEN_TTL = 60
MAX_ATTEMPTS = 5
TOLERANCE = 4
PURPOSES = frozenset(("demo", "login"))
RATE_PERIOD_US = 60_000_000
MAX_RATE_LIMIT = 60_000
RATE_DEFAULTS = {"issue_session": 20, "issue_ip": 60, "verify_session": 60, "verify_ip": 120}


def rate_limit(action, scope):
    """Bound capacity so integer microsecond arithmetic cannot be unbounded."""
    configured = getattr(settings, "NOVA_SLIDER_RATE_LIMITS", {})
    if not isinstance(configured, dict):
        raise ValueError("NOVA_SLIDER_RATE_LIMITS must be a dictionary")
    if any(key not in RATE_DEFAULTS for key in configured):
        raise ValueError("NOVA_SLIDER_RATE_LIMITS contains an unknown action/scope key")
    for name, value in configured.items():
        if type(value) is not int or not 1 <= value <= MAX_RATE_LIMIT:
            raise ValueError(f"NOVA_SLIDER_RATE_LIMITS[{name!r}] must be an integer from 1 to {MAX_RATE_LIMIT}")
    key = f"{action}_{scope}"
    return configured.get(key, RATE_DEFAULTS[key])
