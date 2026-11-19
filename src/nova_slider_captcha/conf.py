import logging
import re
from dataclasses import dataclass, replace
from importlib import import_module
from pathlib import Path

from django.conf import settings
from django.apps import apps
from urllib.parse import unquote, urlsplit

from django.utils.encoding import force_str
from django.utils.functional import Promise

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
RATE_DEFAULTS = {"init_ip": 40, "issue_session": 20, "issue_ip": 60, "verify_session": 60, "verify_ip": 120}
MAX_BACKGROUND_IMAGES = 8


def background_images():
    if not settings.configured:
        return ()
    paths = getattr(settings, "NOVA_SLIDER_BACKGROUND_IMAGES", ())
    if not isinstance(paths, (list, tuple)) or len(paths) > MAX_BACKGROUND_IMAGES:
        raise ValueError("NOVA_SLIDER_BACKGROUND_IMAGES 必须是最多包含 8 项的列表或元组")
    for path in paths:
        if (not isinstance(path, str) or not 1 <= len(path) <= 1024
                or path.startswith(("//", "\\")) or any(ord(char) < 32 or ord(char) == 127 for char in path)
                or not Path(path).is_absolute()):
            raise ValueError("NOVA_SLIDER_BACKGROUND_IMAGES 仅接受不含控制字符的绝对本地路径字符串")
    return tuple(paths)


def session_backend():
    """Django's database session engines and their subclasses need the model."""
    if apps.is_installed("django.contrib.sessions"):
        return
    from django.contrib.sessions.backends.db import SessionStore as DatabaseSessionStore
    try:
        store = import_module(settings.SESSION_ENGINE).SessionStore
        database_backed = issubclass(store, DatabaseSessionStore)
    except (ImportError, AttributeError, TypeError, ValueError) as error:
        raise ValueError("SESSION_ENGINE must provide an importable SessionStore class") from error
    if database_backed:
        raise ValueError("Database-backed sessions require django.contrib.sessions in INSTALLED_APPS")


def alternative_link(url=None, label=None):
    """Only explicit host-owned local paths; never read request parameters."""
    if url is None and label is None:
        return None
    if not isinstance(url, (str, Promise)) or not isinstance(label, (str, Promise)):
        raise ValueError("CAPTCHA alternative URL and label must both be strings")
    url, label = force_str(url), force_str(label)
    decoded = unquote(url)
    parsed = urlsplit(decoded)
    if (not url or len(url) > 2048 or not url.startswith("/") or url.startswith("//")
            or not decoded.startswith("/") or decoded.startswith("//")
            or parsed.scheme or parsed.netloc or "\\" in decoded
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in decoded)):
        raise ValueError("CAPTCHA alternative URL must be a local absolute path without a scheme, host, whitespace or backslash")
    if not label.strip() or len(label) > 200 or not label.isprintable():
        raise ValueError("CAPTCHA alternative label must contain 1–200 printable characters")
    return {"url": url, "label": label}


def configured_alternative_link():
    return alternative_link(getattr(settings, "NOVA_SLIDER_ALTERNATIVE_URL", None),
                            getattr(settings, "NOVA_SLIDER_ALTERNATIVE_LABEL", None))


@dataclass(frozen=True)
class ChallengePolicy:
    ttl: int
    max_attempts: int
    tolerance: int


_POLICY_FIELDS = {
    "ttl": ("NOVA_SLIDER_CHALLENGE_TTL", CHALLENGE_TTL, 30, 600),
    "max_attempts": ("NOVA_SLIDER_MAX_ATTEMPTS", MAX_ATTEMPTS, 1, 20),
    "tolerance": ("NOVA_SLIDER_TOLERANCE", TOLERANCE, 0, 10),
}


def _policy_integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def challenge_policy(purpose=None):
    """Validate the whole current table before returning an issuance policy."""
    default = ChallengePolicy(**{
        key: _policy_integer(getattr(settings, name, fallback), name, minimum, maximum)
        for key, (name, fallback, minimum, maximum) in _POLICY_FIELDS.items()
    })
    setting = "NOVA_SLIDER_PURPOSE_POLICIES"
    configured = getattr(settings, setting, {})
    if not isinstance(configured, dict):
        raise ValueError(f"{setting} must be a dictionary")
    if not configured:
        return default
    allowed = purposes()
    selected = default
    for name, overrides in configured.items():
        if not isinstance(name, str) or name not in allowed:
            raise ValueError(f"{setting} may only contain allowed CAPTCHA purposes")
        if not isinstance(overrides, dict):
            raise ValueError(f"{setting}[{name!r}] must be a dictionary")
        if any(key not in _POLICY_FIELDS for key in overrides):
            raise ValueError(f"{setting}[{name!r}] accepts only ttl, max_attempts and tolerance")
        for key, value in overrides.items():
            _, _, minimum, maximum = _POLICY_FIELDS[key]
            _policy_integer(value, f"{setting}[{name!r}][{key!r}]", minimum, maximum)
        if name == purpose:
            selected = replace(default, **overrides)
    return selected


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


def audit_success_enabled():
    value = getattr(settings, "NOVA_SLIDER_AUDIT_SUCCESS", False)
    if type(value) is not bool:
        raise ValueError("NOVA_SLIDER_AUDIT_SUCCESS must be a boolean")
    return value


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
