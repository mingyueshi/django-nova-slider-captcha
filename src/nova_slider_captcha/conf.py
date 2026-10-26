import logging
import re

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


def purposes():
    """Read on every call; a configured collection replaces the defaults."""
    configured = getattr(settings, "NOVA_SLIDER_PURPOSES", PURPOSES)
    if not isinstance(configured, (list, tuple, set, frozenset)) or not configured:
        raise ValueError("NOVA_SLIDER_PURPOSES must be a nonempty list, tuple, set or frozenset")
    if any(not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_:-]{0,31}", name) for name in configured):
        raise ValueError("NOVA_SLIDER_PURPOSES names must match [a-z][a-z0-9_:-]{0,31}")
    return frozenset(configured)


def valid_purpose(value):
    return isinstance(value, str) and value in purposes()


def rate_log_level():
    value = getattr(settings, "NOVA_SLIDER_RATE_LOG_LEVEL", "DEBUG")
    levels = {name: getattr(logging, name) for name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")}
    if not isinstance(value, str) or value not in (*levels, "OFF"):
        raise ValueError("NOVA_SLIDER_RATE_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, CRITICAL or OFF")
    return None if value == "OFF" else levels[value]


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
