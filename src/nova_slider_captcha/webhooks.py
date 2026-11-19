"""Best-effort notifications for committed CAPTCHA state transitions."""
import hashlib
import hmac
import http.client
import json
import os
import re
from threading import BoundedSemaphore, Thread
from time import time
from urllib.parse import urlsplit
from uuid import uuid4

from django.conf import settings
from django.db import transaction

_MAX_IN_FLIGHT = 4
_IO_TIMEOUT = 2
_slots = BoundedSemaphore(_MAX_IN_FLIGHT)


def _reset_slots():
    global _slots
    _slots = BoundedSemaphore(_MAX_IN_FLIGHT)


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_slots)


def webhook_configuration():
    configured = getattr(settings, "NOVA_SLIDER_WEBHOOK", None)
    if configured is None:
        return None
    if type(configured) is not dict or configured.keys() != {"url", "secret"}:
        raise ValueError("NOVA_SLIDER_WEBHOOK 须包含 url 和 secret")
    url, secret = configured["url"], configured["secret"]
    if (
        type(secret) is not str or re.fullmatch(r"[0-9a-f]{64}", secret) is None
        or secret == settings.SECRET_KEY
    ):
        raise ValueError("NOVA_SLIDER_WEBHOOK 的 secret 须为独立的 64 位小写十六进制密钥")
    if (
        type(url) is not str or not 1 <= len(url) <= 2048 or not url.startswith("https://")
        or any(not 33 <= ord(char) <= 126 for char in url) or any(char in url for char in "\\?#")
    ):
        raise ValueError("NOVA_SLIDER_WEBHOOK 的 url 须为 HTTPS 地址且不含认证信息、查询或片段")
    try:
        target = urlsplit(url)
        if (
            target.username is not None or not target.hostname
            or re.fullmatch(r"[a-z0-9.:-]+", target.hostname) is None or target.port == 0
        ):
            raise ValueError
    except ValueError:
        raise ValueError("NOVA_SLIDER_WEBHOOK 的 url 主机或端口无效") from None
    return target.hostname, target.port or 443, target.path or "/", bytes.fromhex(secret)


def _deliver(config, name, slot):
    try:
        hostname, port, path, secret = config
        body = json.dumps({"event": name, "notification_id": uuid4().hex}, separators=(",", ":")).encode("ascii")
        timestamp = str(int(time()))
        signature = hmac.new(secret, timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
        connection = http.client.HTTPSConnection(hostname, port, timeout=_IO_TIMEOUT)
        try:
            # A direct TLS connection neither uses environment proxies nor follows redirects.
            connection.request("POST", path, body, headers={
                "Content-Type": "application/json",
                "X-Nova-Webhook-Timestamp": timestamp,
                "X-Nova-Webhook-Signature": "sha256=" + signature,
            })
            # Never read a response body or retry; any status ends this attempt.
            with connection.getresponse():
                pass
        finally:
            connection.close()
    except Exception:
        # Delivery and failure details are isolated from the application's logs.
        pass
    finally:
        slot.release()


def _submit(config, name):
    slot = _slots
    acquired = False
    try:
        if webhook_configuration() != config or not slot.acquire(blocking=False):
            return
        acquired = True
        Thread(target=_deliver, args=(config, name, slot), daemon=True).start()
    except Exception:
        if acquired:
            slot.release()


def webhook_success(name, *, using):
    try:
        config = webhook_configuration()
        if config is not None:
            transaction.on_commit(lambda: _submit(config, name), using=using)
    except Exception:
        # Manually managed transactions outside atomic cannot register hooks.
        # Configuration/registration failures must never change the result.
        pass
