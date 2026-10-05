import json
import math
import uuid
from functools import wraps

from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET

from . import services
from .conf import PURPOSES, WIDTH, PIECE_SIZE


def _failure(code, status=400):
    return JsonResponse({"ok": False, "code": code, "attemptsRemaining": 0}, status=status)


def same_origin(request):
    origin = request.headers.get("Origin")
    if origin and origin != f"{request.scheme}://{request.get_host()}":
        return False
    return request.headers.get("Sec-Fetch-Site") not in ("cross-site", "same-site")


def json_post(view):
    @wraps(view)
    @never_cache
    @csrf_protect
    def wrapped(request):
        if request.method != "POST":
            response = _failure("method_not_allowed", 405)
            response["Allow"] = "POST"
            return response
        if not same_origin(request):
            return _failure("origin_rejected", 403)
        if request.content_type != "application/json":
            return _failure("json_required", 415)
        try:
            content_length = int(request.META.get("CONTENT_LENGTH") or 0)
        except (ValueError, TypeError):
            return _failure("invalid_content_length")
        if content_length > 4096:
            return _failure("request_too_large", 413)
        try:
            if len(request.body) > 4096:
                return _failure("request_too_large", 413)
            data = json.loads(request.body)
        except (ValueError, UnicodeError, RecursionError):
            return _failure("invalid_json")
        if not isinstance(data, dict):
            return _failure("invalid_json")
        if not services.session_binding(request):
            return _failure("init_required", 409)
        return view(request, data)
    return wrapped


@never_cache
@require_GET
@ensure_csrf_cookie
def init(request):
    if not same_origin(request):
        return _failure("origin_rejected", 403)
    services.session_binding(request, create=True)
    return JsonResponse({"csrfToken": get_token(request)})


@json_post
def challenge(request, data):
    if not services.allow_request(request, "issue"):
        response = _failure("rate_limited", 429)
        response["Retry-After"] = "60"
        return response
    purpose = data.get("purpose")
    if not isinstance(purpose, str) or purpose not in PURPOSES:
        return _failure("invalid_purpose")
    return JsonResponse(services.issue(request, purpose))


@json_post
def verify(request, data):
    if not services.allow_request(request, "verify"):
        response = _failure("rate_limited", 429)
        response["Retry-After"] = "60"
        return response
    try:
        raw_id = data.get("challengeId")
        if not isinstance(raw_id, str) or len(raw_id) != 36:
            raise ValueError
        challenge_id = uuid.UUID(raw_id)
    except (ValueError, TypeError, AttributeError):
        return _failure("invalid_challenge")
    x = data.get("x")
    if type(x) not in (int, float) or not 0 <= x <= WIDTH - PIECE_SIZE or not math.isfinite(x):
        return _failure("invalid_position")
    return JsonResponse(services.verify(request, challenge_id, x))


@json_post
def submit(request, data):
    # Fixed trusted purpose; client input can never choose a privileged operation.
    if data.get("purpose") != "demo":
        return _failure("invalid_purpose")
    if not services.consume(data.get("token"), request, purpose="demo"):
        return _failure("invalid_token", 403)
    return JsonResponse({"ok": True, "message": "Verification accepted. This proof has now been consumed."})


@never_cache
@ensure_csrf_cookie
@require_GET
def demo(request):
    services.session_binding(request, create=True)
    return render(request, "nova_slider_captcha/demo.html")
