from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.metrics import MetricsRegistry


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, metrics: MetricsRegistry) -> None:
        super().__init__(app)
        self.metrics = metrics

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid4()))[:64]
        request.state.request_id = request_id
        started = time.perf_counter()
        self.metrics.increment("http_requests_total")

        try:
            response = await call_next(request)
        except Exception:
            self.metrics.increment("http_unhandled_errors_total")
            raise
        finally:
            self.metrics.observe_latency((time.perf_counter() - started) * 1000)

        if response.status_code >= 500:
            self.metrics.increment("http_5xx_total")
        elif response.status_code >= 400:
            self.metrics.increment("http_4xx_total")

        headers = response.headers
        headers["X-Request-ID"] = request_id
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "no-referrer"
        headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        headers["Cache-Control"] = "no-store"
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, max_body_bytes: int) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > self.max_body_bytes
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length header"}, status_code=400)
            if too_large:
                return JSONResponse({"detail": "Request body is too large"}, status_code=413)
        return await call_next(request)


class SlidingWindowRateLimitMiddleware(BaseHTTPMiddleware):
    """Single-process rate limiter suitable for this demo deployment."""

    def __init__(self, app: object, requests: int, window_seconds: int) -> None:
        super().__init__(app)
        self.requests = requests
        self.window_seconds = window_seconds
        self._events: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in {"/healthz", "/readyz"}:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            events = self._events[client_ip]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.requests:
                retry_after = max(1, round(events[0] + self.window_seconds - now))
                return JSONResponse(
                    {"detail": "Too many requests. Please try again shortly."},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)

        return await call_next(request)
