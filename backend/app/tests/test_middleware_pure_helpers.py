"""
Tests for pure helpers on `MetricsMiddleware`.

This middleware is bolted onto the FastAPI app at startup and runs
on every request. Most of its behaviour is async/IO, but it has a
small pure surface that pins observability and recursion-avoidance
contracts:

  - **MetricsMiddleware.EXCLUDED_PATHS**: the constant set of paths
    that bypass metrics collection. CRITICAL — `/metrics` MUST be
    in this set, otherwise the Prometheus scraper recursively
    triggers itself on each scrape, causing exponential request
    duplication. Also pins `/health` (k8s liveness probes flood
    metrics otherwise) and `/openapi.json` / `/docs` / `/redoc`
    (cardinality noise).

5 cases.
"""

from app.middleware.metrics_middleware import MetricsMiddleware

# ─── MetricsMiddleware.EXCLUDED_PATHS ───────────────────────────────


def test_metrics_excluded_paths_contains_metrics():
    # Pin: /metrics MUST be excluded — otherwise Prometheus scraping
    # the metrics endpoint would itself count as a request, causing
    # an unbounded growth loop.
    assert "/metrics" in MetricsMiddleware.EXCLUDED_PATHS


def test_metrics_excluded_paths_contains_health():
    # Pin: /health MUST be excluded — k8s liveness/readiness probes
    # hit this endpoint many times per minute and would dominate
    # the metrics histogram.
    assert "/health" in MetricsMiddleware.EXCLUDED_PATHS


def test_metrics_excluded_paths_contains_docs_endpoints():
    # Pin: OpenAPI / docs endpoints are excluded to prevent dev
    # browser visits from being counted in production metrics.
    assert "/openapi.json" in MetricsMiddleware.EXCLUDED_PATHS
    assert "/docs" in MetricsMiddleware.EXCLUDED_PATHS
    assert "/redoc" in MetricsMiddleware.EXCLUDED_PATHS


def test_metrics_excluded_paths_is_set_not_list():
    # Pin: data structure is a set (O(1) lookup). Pin so a refactor
    # to a list doesn't silently degrade per-request perf.
    assert isinstance(MetricsMiddleware.EXCLUDED_PATHS, set)


def test_metrics_excluded_paths_does_not_exclude_application_endpoints():
    # Pin: API endpoints under /api/ ARE measured. If a refactor
    # accidentally added "/" or "/api" to the exclude list, all
    # application traffic would vanish from metrics.
    assert "/api/v1/applications" not in MetricsMiddleware.EXCLUDED_PATHS
    assert "/api/v1/users" not in MetricsMiddleware.EXCLUDED_PATHS
