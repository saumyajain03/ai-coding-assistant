"""
FastAPI Security & Request Middleware
Implements:
1. Security headers (X-Content-Type-Options, X-Frame-Options, CSP, Referrer-Policy).
2. Request ID tracking & propagation (X-Request-ID).
3. In-memory IP-based rate limiting (sliding window/token bucket).
4. Safe structured JSON error handling.
"""

import time
import uuid
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects defensive HTTP security headers into every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self' http://localhost:*;"
        )
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Tracks or generates an X-Request-ID header on each request and response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = req_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Lightweight, deterministic IP-based sliding window rate limiter.
    Enforces settings.RATE_LIMIT_PER_MINUTE per client IP.
    """

    def __init__(self, app, requests_per_minute: int | None = None):
        super().__init__(app)
        settings = get_settings()
        self.limit = requests_per_minute or settings.RATE_LIMIT_PER_MINUTE
        self.window_sec = 60
        self.hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Exclude internal health checks from rate limiting
        if request.url.path in {"/api/v1/health", "/docs", "/openapi.json"}:
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        cutoff = now - self.window_sec

        # Prune old timestamps
        valid_timestamps = [t for t in self.hits[client_ip] if t > cutoff]
        self.hits[client_ip] = valid_timestamps

        if len(valid_timestamps) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": f"Too many requests. Limit is {self.limit} requests per minute.",
                    "request_id": getattr(request.state, "request_id", None),
                },
                headers={"Retry-After": "60"},
            )

        self.hits[client_ip].append(now)
        return await call_next(request)
