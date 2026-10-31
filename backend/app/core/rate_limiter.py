"""Rate Limiting and Abuse Prevention Middleware."""

import time
import logging
from typing import Dict, List, Tuple
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("nexus.security.ratelimit")


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self, default_limit: int = 150, window_seconds: int = 60):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        # Maps client_key -> list of request timestamps
        self._history: Dict[str, List[float]] = {}
        # Route-specific strict overrides (e.g., auth endpoints)
        self._route_limits: Dict[str, Tuple[int, int]] = {
            "/api/v1/auth/login": (60, 60),  # 60 per minute
            "/api/v1/auth/register": (60, 60),
            "/api/v1/memory/wipe": (10, 60),
        }

    def reset(self):
        """Reset history for tests."""
        self._history.clear()


    def is_allowed(self, client_key: str, path: str) -> Tuple[bool, int, int]:
        """Check if request is permitted. Returns (allowed, remaining, retry_after)."""
        now = time.time()
        limit, window = self._route_limits.get(path, (self.default_limit, self.window_seconds))

        if client_key not in self._history:
            self._history[client_key] = []

        # Filter out timestamps outside window
        cutoff = now - window
        self._history[client_key] = [t for t in self._history[client_key] if t > cutoff]

        current_count = len(self._history[client_key])
        if current_count >= limit:
            oldest = self._history[client_key][0]
            retry_after = max(1, int(oldest + window - now))
            return False, 0, retry_after

        self._history[client_key].append(now)
        remaining = limit - current_count - 1
        return True, remaining, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware inspecting request rates and attaching rate-limit headers."""

    def __init__(self, app, limiter: SlidingWindowRateLimiter):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next) -> Response:
        # Exempt health checks and WebSocket upgrades from rate-limiting
        if request.url.path in ["/health", "/api/v1/health"] or request.scope.get("type") == "websocket":
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        allowed, remaining, retry_after = self.limiter.is_allowed(client_ip, request.url.path)

        if not allowed:
            logger.warning(f"Rate limit exceeded for IP {client_ip} on path {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Too Many Requests",
                    "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
