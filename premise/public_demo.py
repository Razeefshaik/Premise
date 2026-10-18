"""Public demo boundaries, independent of verdict evaluation."""
from __future__ import annotations

import asyncio
import time
from contextvars import ContextVar
from starlette.responses import JSONResponse

DISABLED = "Disabled in the public demo. Run Premise locally for the full version."
BANNER = "Public demo on FalkorDB Cloud. Read only. Run locally for GitHub actions and v2."
read_only_request = ContextVar('premise_public_read_only_request', default=False)


class PublicDemoDisabled(PermissionError):
    def __init__(self):
        super().__init__(DISABLED)


def require_private(config):
    if config.public_demo:
        raise PublicDemoDisabled()


class PublicDemoMiddleware:
    """Bound raw bodies before parsing; never trust client-supplied forwarded headers.

    Single-process limits. Unknown proxy addresses share a bucket conservatively.
    Exhausted IP-table capacity rejects new clients rather than evicting active limits.
    """
    def __init__(self, app, *, allowed_posts=("/api/check", "/api/ask"), limit=30,
                 body_limit=65536, clock=time.monotonic):
        self.app, self.allowed_posts = app, set(allowed_posts)
        self.limit, self.body_limit, self.clock = limit, body_limit, clock
        self.windows = {}
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        async def reject(status, detail, headers=None):
            await JSONResponse({"detail": detail}, status_code=status, headers=headers)(scope, receive, send)
        method, path = scope["method"], scope["path"].rstrip("/")
        if method not in {"GET", "HEAD", "OPTIONS"} and not (method == "POST" and path in self.allowed_posts):
            return await reject(403, DISABLED)
        # Raw content-length is only an early check; actual streamed bytes are counted below.
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    size = int(value)
                except ValueError:
                    return await reject(400, "Invalid Content-Length")
                if size < 0 or size > self.body_limit:
                    return await reject(413, "Request body too large")
        expensive = path.startswith("/api/") or path == "/"
        if expensive:
            now = self.clock()
            self.windows = {k: v for k, v in self.windows.items() if now - v[0] < 60}
            ip = (scope.get("client") or ("unknown",))[0]
            category = "proposal" if path in self.allowed_posts else "read"
            key = (ip, category)
            if key not in self.windows and len(self.windows) >= 2048:
                return await reject(429, "Demo is busy; try again in a minute", {"Retry-After": "60"})
            start, used = self.windows.get(key, (now, 0))
            maximum = self.limit if category == "proposal" else 120
            if used >= maximum or self.active >= 4:
                return await reject(429, "Too many demo requests; try again shortly", {"Retry-After": "60"})
            self.windows[key] = (start, used + 1)
            self.active += 1
        try:
            async def body():
                chunks, size = [], 0
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return None
                    data = message.get("body", b"")
                    size += len(data)
                    if size > self.body_limit:
                        return False
                    chunks.append(data)
                    if not message.get("more_body", False):
                        return b"".join(chunks)
            try:
                data = await asyncio.wait_for(body(), timeout=10)
            except asyncio.TimeoutError:
                return await reject(408, "Request body timed out")
            if data is False:
                return await reject(413, "Request body too large")
            if data is None:
                return
            delivered = False
            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": data, "more_body": False}
                return await receive()
            token = read_only_request.set(True)
            try:
                await self.app(scope, bounded_receive, send)
            finally:
                read_only_request.reset(token)
        finally:
            if expensive:
                self.active -= 1
