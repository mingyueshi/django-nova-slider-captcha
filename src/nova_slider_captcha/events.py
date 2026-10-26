"""Low-cardinality business events. Never pass request data or exception text."""
import logging

from .conf import purposes, rate_log_level

logger = logging.getLogger("nova_slider_captcha")
logger.addHandler(logging.NullHandler())


def event(name, reason, status, *, purpose=None, action=None, level=None):
    # All callers supply literal event/reason/action codes. Purposes are logged
    # only after allowlist validation; invalid client values never reach a sink.
    try:
        allowed = purposes()
    except ValueError:
        allowed = ()
    extra = {"captcha_event": name, "captcha_reason": reason, "captcha_status": status,
             "captcha_purpose": purpose if isinstance(purpose, str) and purpose in allowed else "unknown",
             "captcha_action": action or "none"}
    try:
        logger.log(level if level is not None else logging.ERROR if status >= 500 else logging.WARNING,
                   "CAPTCHA business event", extra=extra)
    except Exception:
        # A broken host logging handler must not change atomicity or availability.
        pass


def rate_denied(action):
    try:
        level = rate_log_level()
    except ValueError:
        level = logging.DEBUG
    if level is not None:
        event("rate_limit", "rate_limited", 429, action=action, level=level)
