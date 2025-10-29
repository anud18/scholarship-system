"""
Prometheus Metrics for Scholarship Management System

This module defines all Prometheus metrics for monitoring application performance,
database health, and business operations.

Metrics Categories:
1. HTTP Metrics - Request count, duration, status codes
2. Database Metrics - Connection pool, query performance
3. Business Metrics - Application counts, email statistics, file uploads
4. Error Metrics - Error rates, authentication failures
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, Info, generate_latest

# =============================================================================
# HTTP METRICS
# =============================================================================

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method"],
)

# =============================================================================
# DATABASE METRICS
# =============================================================================

db_pool_size = Gauge(
    "db_pool_size",
    "Database connection pool size",
    ["pool_type"],  # async, sync
)

db_pool_checked_out = Gauge(
    "db_pool_checked_out",
    "Number of database connections currently checked out",
    ["pool_type"],
)

db_pool_checked_in = Gauge(
    "db_pool_checked_in",
    "Number of database connections currently checked in (available)",
    ["pool_type"],
)

db_pool_overflow = Gauge(
    "db_pool_overflow",
    "Number of overflow connections (exceeding pool size)",
    ["pool_type"],
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],  # select, insert, update, delete
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

db_connections_total = Counter(
    "db_connections_total",
    "Total number of database connections created",
    ["pool_type"],
)

# =============================================================================
# BUSINESS METRICS
# =============================================================================

scholarship_applications_total = Counter(
    "scholarship_applications_total",
    "Total number of scholarship applications",
    ["status"],  # draft, submitted, approved, rejected
)

scholarship_reviews_total = Counter(
    "scholarship_reviews_total",
    "Total number of scholarship reviews",
    ["reviewer_type", "action"],  # professor/college, approve/reject/return
)

email_sent_total = Counter(
    "email_sent_total",
    "Total number of emails sent",
    ["category", "status"],  # category: application/notification/etc, status: success/failed
)

file_uploads_total = Counter(
    "file_uploads_total",
    "Total number of file uploads",
    ["file_type", "status"],  # pdf/image/etc, success/failed
)

payment_rosters_total = Counter(
    "payment_rosters_total",
    "Total number of payment rosters processed",
    ["status"],  # draft, processing, completed, failed
)

# =============================================================================
# ERROR METRICS
# =============================================================================

http_errors_total = Counter(
    "http_errors_total",
    "Total number of HTTP errors",
    ["status_code", "endpoint"],
)

auth_attempts_total = Counter(
    "auth_attempts_total",
    "Total number of authentication attempts",
    ["method", "result"],  # password/sso, success/failed
)

validation_errors_total = Counter(
    "validation_errors_total",
    "Total number of validation errors",
    ["endpoint"],
)

# =============================================================================
# SYSTEM INFO METRICS
# =============================================================================

app_info = Info("app_info", "Application information")

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def normalize_endpoint(path: str) -> str:
    """
    Normalize endpoint path to reduce cardinality.

    Replaces path parameters with placeholders:
    - /api/v1/applications/123 -> /api/v1/applications/:id
    - /api/v1/scholarships/abc-def -> /api/v1/scholarships/:id

    Args:
        path: Request path

    Returns:
        Normalized path with parameters replaced
    """
    import re

    # Skip if already normalized or is a static path
    if ":id" in path or path.endswith(("/health", "/metrics", "/docs", "/openapi.json")):
        return path

    # Replace UUID patterns
    path = re.sub(
        r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "/:id",
        path,
        flags=re.IGNORECASE,
    )

    # Replace numeric IDs
    path = re.sub(r"/\d+", "/:id", path)

    # Replace alphanumeric IDs (at least 8 characters)
    path = re.sub(r"/[a-zA-Z0-9_-]{8,}", "/:id", path)

    return path


def update_db_pool_metrics():
    """
    Update database connection pool metrics.

    Should be called periodically or on-demand to collect current pool status.
    """
    try:
        from app.db.session import async_engine, sync_engine

        # Update async pool metrics
        async_pool = async_engine.pool
        db_pool_size.labels(pool_type="async").set(async_pool.size())
        db_pool_checked_out.labels(pool_type="async").set(async_pool.checkedout())
        db_pool_checked_in.labels(pool_type="async").set(async_pool.checkedin())
        db_pool_overflow.labels(pool_type="async").set(async_pool.overflow())

        # Update sync pool metrics
        sync_pool = sync_engine.pool
        db_pool_size.labels(pool_type="sync").set(sync_pool.size())
        db_pool_checked_out.labels(pool_type="sync").set(sync_pool.checkedout())
        db_pool_checked_in.labels(pool_type="sync").set(sync_pool.checkedin())
        db_pool_overflow.labels(pool_type="sync").set(sync_pool.overflow())

    except Exception:  # pylint: disable=broad-exception-caught
        # Silently fail to avoid breaking metrics collection
        pass


def set_app_info(app_name: str, version: str, environment: str):
    """
    Set application information metrics.

    Args:
        app_name: Application name
        version: Application version
        environment: Environment (dev/staging/production)
    """
    app_info.info(
        {
            "app_name": app_name,
            "version": version,
            "environment": environment,
        }
    )


# Export all for convenience
__all__ = [
    # HTTP Metrics
    "http_requests_total",
    "http_request_duration_seconds",
    "http_requests_in_progress",
    # Database Metrics
    "db_pool_size",
    "db_pool_checked_out",
    "db_pool_checked_in",
    "db_pool_overflow",
    "db_query_duration_seconds",
    "db_connections_total",
    # Business Metrics
    "scholarship_applications_total",
    "scholarship_reviews_total",
    "email_sent_total",
    "file_uploads_total",
    "payment_rosters_total",
    # Error Metrics
    "http_errors_total",
    "auth_attempts_total",
    "validation_errors_total",
    # System Info
    "app_info",
    # Helper Functions
    "normalize_endpoint",
    "update_db_pool_metrics",
    "set_app_info",
    # Prometheus exports
    "generate_latest",
    "CONTENT_TYPE_LATEST",
]
