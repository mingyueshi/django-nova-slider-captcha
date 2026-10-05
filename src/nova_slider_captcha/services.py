"""Database-backed issuance, comparison and single-use proof consumption.

Conditional SQL UPDATEs are the correctness boundary. No local-memory/cache lock,
read-then-delete token, or select_for_update assumption is used.
"""
import secrets
from datetime import timedelta

from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .conf import CHALLENGE_TTL, MAX_ATTEMPTS, PURPOSES, TOKEN_TTL, TOLERANCE, rate_limit
from .images import make_puzzle
from .models import Challenge, RateBucket

_SESSION_KEY = "_nova_slider_binding"


def _hash(value, salt="binding"):
    return salted_hmac("nova_slider_captcha." + salt, value, algorithm="sha256").hexdigest()


def session_binding(request, create=False):
    nonce = request.session.get(_SESSION_KEY)
    if not nonce and create:
        nonce = secrets.token_urlsafe(32)
        request.session[_SESSION_KEY] = nonce
    return _hash(nonce) if isinstance(nonce, str) and nonce else None


def allow_request(request, action):
    """Fixed 60-second windows, both per-session and per-direct-peer IP.

    REMOTE_ADDR is authoritative. Forwarded headers are intentionally ignored;
    configure the trusted reverse proxy to set REMOTE_ADDR correctly.
    """
    now = timezone.now()
    window = int(now.timestamp()) // 60
    subjects = {"session": session_binding(request, create=True), "ip": _hash(request.META.get("REMOTE_ADDR", "unknown"), "ip")}
    for scope, subject in subjects.items():
        key = f"{action}:{scope}:{window}:{subject}"
        bucket, _ = RateBucket.objects.get_or_create(key=key, defaults={"expires_at": now + timedelta(seconds=120)})
        if not RateBucket.objects.filter(pk=bucket.pk, count__lt=rate_limit(action, scope)).update(count=F("count") + 1):
            return False
    return True


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
