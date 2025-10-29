"""
Prometheus Metrics Middleware for FastAPI

This middleware automatically collects HTTP request metrics including:
- Request count by method, endpoint, and status code
- Request duration/latency
- Requests in progress
- HTTP error rates

The middleware is exception-safe and will not affect application behavior
even if metrics collection fails.
"""

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.metrics import (
    http_errors_total,
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
    normalize_endpoint,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect Prometheus metrics for HTTP requests.

    This middleware:
    1. Tracks request count, duration, and status codes
    2. Monitors requests in progress
    3. Records HTTP errors
    4. Normalizes endpoints to reduce cardinality
    5. Excludes monitoring endpoints to avoid recursion

    Usage:
        app.add_middleware(MetricsMiddleware)
    """

    # Endpoints to exclude from metrics (to avoid infinite loops and noise)
    EXCLUDED_PATHS = {"/metrics", "/health", "/openapi.json", "/docs", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        """
        Process each HTTP request and collect metrics.

        Args:
            request: FastAPI request object
            call_next: Next middleware or route handler

        Returns:
            Response from the application
        """
        # Skip metrics collection for excluded paths
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # Extract request metadata
        method = request.method
        path = request.url.path

        # Normalize endpoint to reduce label cardinality
        # Example: /api/v1/applications/123 -> /api/v1/applications/:id
        endpoint = normalize_endpoint(path)

        # Track in-progress requests
        http_requests_in_progress.labels(method=method).inc()

        # Record start time
        start_time = time.perf_counter()

        try:
            # Process request
            response: Response = await call_next(request)
            status_code = response.status_code

        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Record error metric
            try:
                http_errors_total.labels(
                    status_code="500",
                    endpoint=endpoint,
                ).inc()
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # Silently fail to avoid breaking the application

            # Re-raise the exception to let FastAPI handle it
            raise exc

        finally:
            # Calculate request duration
            duration = time.perf_counter() - start_time

            # Update metrics (wrapped in try-except to be exception-safe)
            try:
                # Record request count
                http_requests_total.labels(
                    method=method,
                    endpoint=endpoint,
                    status=str(status_code),
                ).inc()

                # Record request duration
                http_request_duration_seconds.labels(
                    method=method,
                    endpoint=endpoint,
                ).observe(duration)

                # Record errors (4xx and 5xx)
                if status_code >= 400:
                    http_errors_total.labels(
                        status_code=str(status_code),
                        endpoint=endpoint,
                    ).inc()

                # Decrement in-progress counter
                http_requests_in_progress.labels(method=method).dec()

            except Exception:  # pylint: disable=broad-exception-caught
                # Silently fail to avoid breaking the application
                pass

        return response
