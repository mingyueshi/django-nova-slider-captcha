"""ASGI adapter contract probe only; no sockets, services or real IP data."""
import asyncio
import io
import json
from pathlib import Path
from importlib.metadata import version
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
from django.core.handlers.asgi import ASGIRequest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

async def probe(peer):
    result = {}
    async def app(scope, receive, send):
        request = ASGIRequest(scope, io.BytesIO())
        result.update(remote_addr=request.META["REMOTE_ADDR"], scheme=request.scheme)
    middleware = ProxyHeadersMiddleware(app, trusted_hosts=["127.0.0.1"])
    scope = {"type": "http", "method": "GET", "path": "/", "query_string": b"", "scheme": "http", "server": ("testserver", 80), "client": (peer, 1234), "headers": [(b"x-forwarded-for", b"203.0.113.23"), (b"x-forwarded-proto", b"https"), (b"x-real-ip", b"192.0.2.99")]}
    await middleware(scope, None, None)
    return result

async def main():
    trusted = await probe("127.0.0.1")
    untrusted = await probe("198.51.100.12")
    assert trusted == {"remote_addr": "203.0.113.23", "scheme": "https"}
    assert untrusted == {"remote_addr": "198.51.100.12", "scheme": "http"}
    output = {"uvicorn": version("uvicorn"), "django": version("Django"), "trusted_proxy_maps_scope_to_meta": True, "untrusted_peer_cannot_forge_meta": True, "x_real_ip_does_not_override": True, "limitations": "Synthetic middleware/ASGIRequest contract only; no Nginx, uWSGI or actual deployment tested"}
    Path(__file__).with_name("proxy-probe.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output))
asyncio.run(main())
