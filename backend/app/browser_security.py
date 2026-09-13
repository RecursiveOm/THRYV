import time
from collections import OrderedDict

from starlette.responses import JSONResponse


class BrowserSecurity:
    """Exact Origin + a non-simple header protect all cookie-authenticated mutations."""

    def __init__(self, app, origin: str, auth_limit: int = 20):
        self.app = app
        self.origin = origin
        self.auth_limit = auth_limit
        self.attempts = OrderedDict()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        headers = dict(scope["headers"])
        browser_api = path.startswith(
            (
                "/api/auth/",
                "/api/account",
                "/api/conversations",
                "/api/devices",
                "/api/actions",
                "/api/memories",
                "/api/voice",
            )
        )
        if browser_api and scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            if (
                headers.get(b"origin", b"").decode() != self.origin
                or headers.get(b"x-thryv-request") != b"1"
            ):
                return await JSONResponse(
                    {"error": {"code": "csrf_rejected", "message": "Request origin was rejected."}},
                    status_code=403,
                )(scope, receive, send)
        # Bounded, per-process IP buckets protect password hashing and token redemption.
        if scope["method"] == "POST" and path in (
            "/api/auth/login",
            "/api/auth/register",
            "/api/companion/pair",
        ):
            identity = (scope.get("client") or ("unknown", 0))[0]
            current = time.monotonic()
            attempts, start = self.attempts.pop(identity, (0, current))
            if current - start > 60:
                attempts, start = 0, current
            self.attempts[identity] = (attempts + 1, start)
            if len(self.attempts) > 10000:
                self.attempts.popitem(last=False)
            if attempts >= self.auth_limit:
                return await JSONResponse(
                    {
                        "error": {
                            "code": "rate_limited",
                            "message": "Wait a minute before trying again.",
                        }
                    },
                    status_code=429,
                )(scope, receive, send)
        await self.app(scope, receive, send)
