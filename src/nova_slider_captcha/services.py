"""Database-backed issuance, comparison and single-use proof consumption.

Conditional SQL UPDATEs are the correctness boundary. No local-memory/cache lock,
read-then-delete token, or select_for_update assumption is used.
"""
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.db import router
from django.db.models import BigIntegerField, F, Value
from django.db.models.functions import Greatest
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .conf import CHALLENGE_TTL, MAX_ATTEMPTS, PURPOSES, RATE_PERIOD_US, TOKEN_TTL, TOLERANCE, rate_limit
from .images import make_puzzle
from .models import Challenge, RateLimitState

_SESSION_KEY = "_nova_slider_binding"


def _hash(value, salt="binding"):
    return salted_hmac("nova_slider_captcha." + salt, value, algorithm="sha256").hexdigest()


def session_binding(request, create=False):
    nonce = request.session.get(_SESSION_KEY)
    if not nonce and create:
        nonce = secrets.token_urlsafe(32)
        request.session[_SESSION_KEY] = nonce
    return _hash(nonce) if isinstance(nonce, str) and nonce else None


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after: int = 0

    def __bool__(self):
        return self.allowed


def timestamp_us(now):
    """Exact integer UTC microseconds; do not round via float timestamps."""
    if timezone.is_naive(now):
        now = timezone.make_aware(now, timezone.get_default_timezone())
    delta = now - datetime(1970, 1, 1, tzinfo=datetime_timezone.utc)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _retry_after(scopes, now_us):
    # Include already-charged scopes: a later rejection does not refund them.
    states = RateLimitState.objects.using(router.db_for_write(RateLimitState)).filter(key__in=scopes).values("key", "tat_us", "blocked_until_us")
    eligible_us = now_us
    for state in states:
        eligible_us = max(eligible_us, state["tat_us"] - scopes[state["key"]], state["blocked_until_us"])
    return max(1, (eligible_us - now_us + 999_999) // 1_000_000)


def allow_request(request, action):
    """Atomically claim GCRA capacity per direct-peer IP, then per session.

    Each scope starts with N tokens and refills one per ceil(60s/N). Stable
    keys prevent a wall-clock window boundary or a new session resetting IP
    debt. An accepted earlier scope is not refunded if a later scope rejects.
    Denials never advance a scope's TAT. Backward clocks retain debt rather
    than reset it; deployments must synchronize clocks (arbitrary cross-host
    skew is not covered). Database failures propagate and therefore fail closed.

    REMOTE_ADDR is authoritative. Forwarded headers are intentionally ignored;
    configure the trusted reverse proxy to set REMOTE_ADDR correctly.
    """
    limits = {scope: rate_limit(action, scope) for scope in ("ip", "session")}
    now_us = timestamp_us(timezone.now())
    subjects = (("ip", _hash(request.META.get("REMOTE_ADDR", "unknown"), "ip")),
                ("session", session_binding(request, create=True)))
    claimed = {}
    for scope, subject in subjects:
        capacity = limits[scope]
        interval_us = (RATE_PERIOD_US + capacity - 1) // capacity
        tolerance_us = (capacity - 1) * interval_us
        key = f"{action}:{scope}:{subject}"
        claimed[key] = tolerance_us
        RateLimitState.objects.get_or_create(key=key)
        updated = RateLimitState.objects.filter(
            key=key, tat_us__lte=now_us + tolerance_us, blocked_until_us__lte=now_us,
        ).update(tat_us=Greatest(F("tat_us"), Value(now_us, output_field=BigIntegerField())) + interval_us)
        if not updated:
            return RateDecision(False, _retry_after(claimed, now_us))
    return RateDecision(True)


def issue(request, purpose):
    if purpose not in PURPOSES:
        raise ValueError("Unsupported CAPTCHA purpose")
    binding = session_binding(request, create=True)
    target_x, piece_y, background, piece = make_puzzle()
    challenge = Challenge.objects.create(session_hash=binding, purpose=purpose, target_x=target_x, expires_at=timezone.now() + timedelta(seconds=CHALLENGE_TTL))
    return {"challengeId": str(challenge.pk), "background": background, "piece": piece, "width": 320, "height": 160, "pieceWidth": 44, "pieceY": piece_y, "expiresIn": CHALLENGE_TTL, "maxAttempts": MAX_ATTEMPTS}


def verify(request, challenge_id, x):
    now = timezone.now()
    binding = session_binding(request)
    challenge = Challenge.objects.filter(pk=challenge_id, session_hash=binding).first() if binding else None
    if not challenge:
        return {"ok": False, "code": "invalid_challenge", "attemptsRemaining": 0}
    if challenge.expires_at <= now:
        return {"ok": False, "code": "expired", "attemptsRemaining": 0}
    if challenge.solved:
        return {"ok": False, "code": "already_verified", "attemptsRemaining": 0}
    if challenge.attempts >= MAX_ATTEMPTS:
        return {"ok": False, "code": "attempts_exhausted", "attemptsRemaining": 0}
    active = Challenge.objects.filter(pk=challenge.pk, session_hash=binding, expires_at__gt=now, solved=False, attempts__lt=MAX_ATTEMPTS)
    if abs(challenge.target_x - x) <= TOLERANCE:
        token = secrets.token_urlsafe(32)
        updated = active.update(attempts=F("attempts") + 1, solved=True, token_hash=_hash(token, "token"), token_expires_at=now + timedelta(seconds=TOKEN_TTL))
        if updated:
            return {"ok": True, "token": token, "expiresIn": TOKEN_TTL}
    else:
        updated = active.update(attempts=F("attempts") + 1)
        if updated:
            challenge.refresh_from_db(fields=["attempts"])
            remaining = max(0, MAX_ATTEMPTS - challenge.attempts)
            return {"ok": False, "code": "incorrect", "attemptsRemaining": remaining}
    return {"ok": False, "code": "invalid_challenge", "attemptsRemaining": 0}


def consume(token, request, purpose):
    """Atomically consume one unexpired token for this session and purpose.

    Call from trusted application code with a fixed purpose before the protected
    operation. Do not trust a client's asserted purpose. Returns bool; database
    failures propagate (fail closed). Business transactions remain your concern.
    """
    if purpose not in PURPOSES or not isinstance(token, str) or len(token) != 43:
        return False
    binding = session_binding(request)
    if not binding:
        return False
    return bool(Challenge.objects.filter(token_hash=_hash(token, "token"), session_hash=binding, purpose=purpose, solved=True, token_consumed=False, token_expires_at__gt=timezone.now()).update(token_consumed=True))
