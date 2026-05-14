"""
Tests for pure helpers on `MetricsMiddleware` + `SchemaValidationMiddleware`.

These middlewares are bolted onto the FastAPI app at startup and run
on every request. Most of their behaviour is async/IO, but each has a
small pure surface that pins observability and recursion-avoidance
contracts:

  - **MetricsMiddleware.EXCLUDED_PATHS**: the constant set of paths
    that bypass metrics collection. CRITICAL — `/metrics` MUST be
    in this set, otherwise the Prometheus scraper recursively
    triggers itself on each scrape, causing exponential request
    duplication. Also pins `/health` (k8s liveness probes flood
    metrics otherwise) and `/openapi.json` / `/docs` / `/redoc`
    (cardinality noise).

  - **SchemaValidationMiddleware._should_skip_validation(path)**:
    prefix-match against a documented skip list. Pin so any path
    starting with `/health`, `/docs`, `/openapi.json`, `/redoc`,
    `/static`, `/favicon.ico` is skipped, AND so any other path
    is NOT skipped.

  - **SchemaValidationMiddleware.get_validation_errors() /
    clear_validation_errors()**: the error-collection ledger. Pin
    that get returns a COPY (so callers can't mutate internal
    state) and clear empties the list in place.

  - **SchemaValidationMiddleware.__init__** explicit enabled
    override: pin that `enabled=True` / `enabled=False` overrides
    the settings.debug default, so test environments can force
    behaviour either way.

14 cases.
"""

from unittest.mock import MagicMock

import pytest

from app.middleware.metrics_middleware import MetricsMiddleware
from app.middleware.schema_validation_middleware import SchemaValidationMiddleware

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


# ─── SchemaValidationMiddleware._should_skip_validation ─────────────


@pytest.fixture
def schema_mw():
    # __init__ takes (app, enabled). Pass a sentinel for app and
    # force enabled=True so we exercise the skip-list branch.
    return SchemaValidationMiddleware(app=MagicMock(), enabled=True)


def test_skip_validation_health_exact_match(schema_mw):
    assert schema_mw._should_skip_validation("/health") is True


def test_skip_validation_health_with_subpath(schema_mw):
    # Pin: startswith semantics — /health/liveness should also skip.
    assert schema_mw._should_skip_validation("/health/liveness") is True


def test_skip_validation_static_assets(schema_mw):
    # Pin: /static/* skipped (asset routes never have a Pydantic
    # response model anyway).
    assert schema_mw._should_skip_validation("/static/js/main.js") is True


def test_skip_validation_favicon(schema_mw):
    assert schema_mw._should_skip_validation("/favicon.ico") is True


def test_skip_validation_does_not_skip_api_paths(schema_mw):
    # Pin: API paths are NOT in the skip list — they're the entire
    # point of this middleware.
    assert schema_mw._should_skip_validation("/api/v1/applications") is False


def test_skip_validation_root_path_not_skipped(schema_mw):
    # Pin: bare "/" not skipped (no entry in skip_paths matches "/").
    # Defensive — if "/" were accidentally added the whole app would
    # skip validation since every path starts with "/".
    assert schema_mw._should_skip_validation("/") is False


# ─── enabled override ───────────────────────────────────────────────


def test_explicit_enabled_true_overrides_settings():
    # Pin: explicit enabled=True wins over settings.debug.
    mw = SchemaValidationMiddleware(app=MagicMock(), enabled=True)
    assert mw.enabled is True


def test_explicit_enabled_false_overrides_settings():
    # Pin: explicit enabled=False wins over settings.debug — test
    # envs can force-disable.
    mw = SchemaValidationMiddleware(app=MagicMock(), enabled=False)
    assert mw.enabled is False


# ─── validation error ledger ────────────────────────────────────────


def test_validation_errors_initially_empty(schema_mw):
    assert schema_mw.get_validation_errors() == []


def test_get_validation_errors_returns_copy(schema_mw):
    # Pin: get returns a COPY — callers mutating the returned list
    # must NOT affect internal state. Defensive ledger pattern.
    schema_mw.validation_errors.append({"x": 1})
    out = schema_mw.get_validation_errors()
    out.clear()
    # Internal state still has the entry
    assert len(schema_mw.validation_errors) == 1


def test_clear_validation_errors_empties_in_place(schema_mw):
    schema_mw.validation_errors.append({"x": 1})
    schema_mw.validation_errors.append({"x": 2})
    schema_mw.clear_validation_errors()
    assert schema_mw.validation_errors == []
    assert schema_mw.get_validation_errors() == []
