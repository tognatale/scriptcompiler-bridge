import logging
import re

from starlette.responses import JSONResponse
from starlette.websockets import WebSocketClose

from .config import CORS_ALLOW_ORIGIN_REGEX

logger = logging.getLogger(__name__)

_ORIGIN_RE = re.compile(CORS_ALLOW_ORIGIN_REGEX)
_ANY_HOST = {"0.0.0.0", "::"}
_allowed_hosts = {"127.0.0.1", "localhost"}


def allow_bind_host(host):
    _allowed_hosts.add(host.strip().lower())


def is_allowed_origin(origin):
    return _ORIGIN_RE.fullmatch(origin) is not None


def _host_name(host_header):
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.split(":", 1)[0]


def is_allowed_host(host_header):
    if _allowed_hosts & _ANY_HOST:
        return True
    return _host_name(host_header) in _allowed_hosts


class RequestGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "")
        origin = headers.get("origin")

        if is_allowed_host(host) and (origin is None or is_allowed_origin(origin)):
            await self.app(scope, receive, send)
            return

        logger.warning("Blocked %s %s (host=%r, origin=%r)", scope["type"], scope["path"], host, origin)
        if scope["type"] == "websocket":
            await WebSocketClose(code=1008)(scope, receive, send)
        else:
            await JSONResponse({"error": "Forbidden"}, status_code=403)(scope, receive, send)
