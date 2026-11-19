"""Low-cardinality business events. Never pass request data or exception text."""
import logging
from functools import partial
from threading import Lock
from time import monotonic

from django.db import transaction
from django.db.transaction import TransactionManagementError

from .conf import audit_success_enabled, purposes, rate_log_level

logger = logging.getLogger("nova_slider_captcha")
logger.addHandler(logging.NullHandler())

# One timestamp, independent of configuration contents: fixed memory and at most
# one warning per five minutes per process, even under concurrent form renders.
_optional_link_warning_lock = Lock()
_optional_link_next_warning = 0.0


def optional_link_invalid():
    global _optional_link_next_warning
    now = monotonic()
    with _optional_link_warning_lock:
        if now < _optional_link_next_warning:
            return
        _optional_link_next_warning = now + 300
    # Claim the slot before logging; broken handlers must not retry every render.
    event("optional_link", "configuration_invalid", 200, action="render")


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


def audit_success(action, *, purpose, using):
    try:
        if audit_success_enabled():
            transaction.on_commit(
                partial(event, action, "success", 200, purpose=purpose, action=action, level=logging.INFO),
                using=using,
            )
    except (ValueError, TransactionManagementError):
        # An invalid audit flag or a manually managed connection without an
        # atomic block cannot safely emit this event.
        pass
