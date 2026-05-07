# Phase 3 Backend Metric Instrumentation Plan

Generated: 2026-05-06
Branch: feat/monitoring-phase2
Scope: Wire 9 dead metrics identified in Phase 1 audit (findings F-APP-01, F-APP-02, F-APP-04, F-APP-06, F-GRAF-03, F-GRAF-04, F-GRAF-10)

---

## Audit Finding: http_errors_total Is NOT Dead

Grepping confirmed `backend/app/middleware/metrics_middleware.py` already imports and calls
`http_errors_total` at lines 84-87 (exception path) and 115-118 (4xx/5xx response path).
F-GRAF-03 dashboard panel concern is therefore **not** a missing counter — the metric exists
and is instrumented. No action needed here.

**Confirmed dead metrics (zero callsites outside metrics.py itself):**

| Metric | Type | Labels |
|---|---|---|
| `db_query_duration_seconds` | Histogram | `operation` |
| `db_connections_total` | Counter | `pool_type` |
| `scholarship_applications_total` | Counter | `status` |
| `scholarship_reviews_total` | Counter | `reviewer_type`, `action` |
| `email_sent_total` | Counter | `category`, `status` |
| `file_uploads_total` | Counter | `file_type`, `status` |
| `payment_rosters_total` | Counter | `status` |
| `auth_attempts_total` | Counter | `method`, `result` |
| `validation_errors_total` | Counter | `endpoint` |

---

## Priority 1 — Dashboard-Affecting (instrument in Phase 3 PR-A)

### M1. `db_query_duration_seconds` (F-APP-04, F-GRAF-04)

**Where:** `backend/app/db/session.py` — add SQLAlchemy sync-engine event listeners after
the existing `connect` listener at line 224. The async engine uses asyncpg which does not
expose before/after cursor execute events; instrument the sync engine only (used by Alembic
migrations and background sync tasks). For the async path, wrap at the service layer using
a context-manager helper.

**Patch — sync engine event listener (session.py after line 233):**

```python
import time as _time
from app.core.metrics import db_query_duration_seconds as _db_query_hist

_query_start_times: dict = {}

@event.listens_for(sync_engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    _query_start_times[id(cursor)] = _time.perf_counter()

@event.listens_for(sync_engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start = _query_start_times.pop(id(cursor), None)
    if start is None:
        return
    duration = _time.perf_counter() - start
    op = statement.strip().split()[0].lower()   # select / insert / update / delete
    op = op if op in {"select", "insert", "update", "delete"} else "other"
    _db_query_hist.labels(operation=op).observe(duration)
```

**Patch — async service helper (new file `backend/app/core/db_metrics.py`):**

```python
import time
from contextlib import asynccontextmanager
from app.core.metrics import db_query_duration_seconds

@asynccontextmanager
async def observe_query(operation: str):
    """Wrap async DB calls to record query duration."""
    start = time.perf_counter()
    try:
        yield
    finally:
        db_query_duration_seconds.labels(operation=operation).observe(
            time.perf_counter() - start
        )
```

Usage at key hot-path in `application_service.py` (example around line 1210):

```python
from app.core.db_metrics import observe_query

async with observe_query("select"):
    result = await self.db.execute(stmt)
```

**Test stub:**

```python
# backend/app/tests/test_metrics_db.py
import pytest
from prometheus_client import REGISTRY

def test_db_query_duration_observed_after_sync_query(sync_db_session):
    before = REGISTRY.get_sample_value(
        "db_query_duration_seconds_count", {"operation": "select"}
    ) or 0
    sync_db_session.execute(text("SELECT 1"))
    after = REGISTRY.get_sample_value(
        "db_query_duration_seconds_count", {"operation": "select"}
    ) or 0
    assert after > before
```

**LOC estimate:** ~30 (session.py) + 15 (db_metrics.py) + 20 (test) = 65 LOC
**PR scope:** Small

---

### M2. `scholarship_applications_total` (F-GRAF-10)

**Where:** `backend/app/services/application_service.py`

- `submit_application()` line ~1260 (after `application.status` is set to `submitted`)
- `update_application_status()` line ~1574 (after `application.status` is assigned)

**Patch — submit_application (add after status is committed):**

```python
from app.core.metrics import scholarship_applications_total

# Inside submit_application, after db commit:
scholarship_applications_total.labels(status="submitted").inc()
```

**Patch — update_application_status (after status assignment ~line 1569):**

```python
from app.core.metrics import scholarship_applications_total

scholarship_applications_total.labels(status=status_update.status.value).inc()
```

**Test stub:**

```python
# backend/app/tests/test_metrics_application.py
async def test_submit_increments_applications_total(client, app_factory, db):
    before = REGISTRY.get_sample_value(
        "scholarship_applications_total_total", {"status": "submitted"}
    ) or 0
    await application_service.submit_application(app_id, user)
    after = REGISTRY.get_sample_value(
        "scholarship_applications_total_total", {"status": "submitted"}
    ) or 0
    assert after == before + 1

async def test_approve_increments_applications_total(client, app_factory, db):
    before = REGISTRY.get_sample_value(
        "scholarship_applications_total_total", {"status": "approved"}
    ) or 0
    await application_service.update_application_status(app_id, admin_user, approved_update)
    after = REGISTRY.get_sample_value(
        "scholarship_applications_total_total", {"status": "approved"}
    ) or 0
    assert after == before + 1
```

**LOC estimate:** ~10 (service) + 25 (tests) = 35 LOC
**PR scope:** Small

---

### M3. `email_sent_total` (F-GRAF-10)

**Where:** `backend/app/services/email_management_service.py`, inside
`process_scheduled_emails()`, lines 459-469.

**Patch — after mark_as_sent() at line 459:**

```python
from app.core.metrics import email_sent_total

# success path (line ~460):
scheduled_email.mark_as_sent()
stats["sent"] += 1
email_sent_total.labels(
    category=scheduled_email.email_category or "system",
    status="success",
).inc()

# failure path (line ~468):
scheduled_email.mark_as_failed(str(e))
stats["failed"] += 1
email_sent_total.labels(
    category=scheduled_email.email_category or "system",
    status="failed",
).inc()
```

**Test stub:**

```python
# backend/app/tests/test_metrics_email.py
async def test_email_sent_total_increments_on_success(db, mock_email_service):
    mock_email_service.send_email = AsyncMock(return_value=True)
    before = REGISTRY.get_sample_value(
        "email_sent_total_total", {"category": "application", "status": "success"}
    ) or 0
    await email_management_service.process_scheduled_emails(db)
    after = REGISTRY.get_sample_value(
        "email_sent_total_total", {"category": "application", "status": "success"}
    ) or 0
    assert after > before

async def test_email_sent_total_increments_on_failure(db, mock_email_service):
    mock_email_service.send_email = AsyncMock(side_effect=Exception("SMTP error"))
    before = REGISTRY.get_sample_value(
        "email_sent_total_total", {"category": "system", "status": "failed"}
    ) or 0
    await email_management_service.process_scheduled_emails(db)
    after = REGISTRY.get_sample_value(
        "email_sent_total_total", {"category": "system", "status": "failed"}
    ) or 0
    assert after > before
```

**LOC estimate:** ~10 (service) + 30 (tests) = 40 LOC
**PR scope:** Small

---

## Priority 2 — Lower Priority (no live dashboard panel depends on them)

### Recommendation Matrix

| Metric | Decision | Rationale |
|---|---|---|
| `auth_attempts_total` | **Instrument (minimal)** | Security-relevant; useful for brute-force alerting in future |
| `scholarship_reviews_total` | **Instrument (minimal)** | Review throughput is a key business KPI; low cost |
| `validation_errors_total` | **Instrument (minimal)** | Already captured in middleware 4xx bucket but no per-endpoint breakdown; keep |
| `file_uploads_total` | **Instrument (minimal)** | Easy single callsite in `upload_application_file_minio` |
| `db_connections_total` | **Delete** | Superseded by `db_pool_size`/`db_pool_checked_out` gauges that `update_db_pool_metrics()` already populates; counter semantics add nothing |
| `payment_rosters_total` | **Defer to Phase 4** | Roster workflow is low-frequency; no dashboard; instrument when roster dashboard is built |

---

### M4. `auth_attempts_total` — Instrument (minimal)

**Where:** `backend/app/services/auth_service.py`

- `authenticate_user()` line ~66 (raise `AuthenticationError`) and line ~71 (success path)
- `portal_sso_verify` endpoint in `auth.py` line ~212 (SSO flow success/failure)

**Patch:**

```python
from app.core.metrics import auth_attempts_total

# In authenticate_user(), success path (after line 70):
auth_attempts_total.labels(method="password", result="success").inc()

# In authenticate_user(), failure path (line 67 raise):
auth_attempts_total.labels(method="password", result="failed").inc()
raise AuthenticationError("Invalid nycu_id or email")

# In portal_sso_verify endpoint, success path:
auth_attempts_total.labels(method="sso", result="success").inc()

# In portal_sso_verify endpoint, exception handler:
auth_attempts_total.labels(method="sso", result="failed").inc()
```

**Test stub:**

```python
async def test_auth_attempts_increments_on_failure(db):
    before = REGISTRY.get_sample_value(
        "auth_attempts_total_total", {"method": "password", "result": "failed"}
    ) or 0
    with pytest.raises(AuthenticationError):
        await auth_service.authenticate_user(bad_credentials)
    after = REGISTRY.get_sample_value(
        "auth_attempts_total_total", {"method": "password", "result": "failed"}
    ) or 0
    assert after == before + 1
```

**LOC estimate:** ~12 (services) + 20 (tests) = 32 LOC

---

### M5. `scholarship_reviews_total` — Instrument (minimal)

**Where:** `backend/app/services/review_service.py`, `create_review()` at line ~428 and
`submit_professor_review()` in `application_service.py` at line ~2673.

**Patch (review_service.py after review is persisted):**

```python
from app.core.metrics import scholarship_reviews_total

scholarship_reviews_total.labels(
    reviewer_type="professor",  # or "college" based on reviewer role
    action=review_data.get("recommendation", "pending"),
).inc()
```

**Test stub:**

```python
async def test_review_total_increments_on_professor_review(db, application, professor_user):
    before = REGISTRY.get_sample_value(
        "scholarship_reviews_total_total",
        {"reviewer_type": "professor", "action": "recommend"},
    ) or 0
    await review_service.create_review(application.id, professor_user, review_data)
    after = REGISTRY.get_sample_value(
        "scholarship_reviews_total_total",
        {"reviewer_type": "professor", "action": "recommend"},
    ) or 0
    assert after == before + 1
```

**LOC estimate:** ~10 (service) + 20 (tests) = 30 LOC

---

### M6. `validation_errors_total` — Instrument (minimal)

**Where:** `backend/app/main.py`, existing `validation_exception_handler` at line ~171.

**Patch (inside handler after line 171):**

```python
from app.core.metrics import validation_errors_total

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    from app.core.metrics import normalize_endpoint
    endpoint = normalize_endpoint(request.url.path)
    validation_errors_total.labels(endpoint=endpoint).inc()
    # ... existing response building
```

**Test stub:**

```python
def test_validation_errors_increments_on_422(test_client):
    before = REGISTRY.get_sample_value(
        "validation_errors_total_total", {"endpoint": "/api/v1/applications/:id"}
    ) or 0
    test_client.post("/api/v1/applications/not-an-int/submit")
    after = REGISTRY.get_sample_value(
        "validation_errors_total_total", {"endpoint": "/api/v1/applications/:id"}
    ) or 0
    assert after > before
```

**LOC estimate:** ~5 (main.py) + 15 (tests) = 20 LOC

---

### M7. `file_uploads_total` — Instrument (minimal)

**Where:** `backend/app/services/application_service.py`, `upload_application_file_minio()`
at line ~1765.

**Patch (after upload_file call):**

```python
from app.core.metrics import file_uploads_total

try:
    object_name, file_size = await minio_service.upload_file(file, application_id, file_type)
    file_uploads_total.labels(file_type=file_type, status="success").inc()
except Exception:
    file_uploads_total.labels(file_type=file_type, status="failed").inc()
    raise
```

**Test stub:**

```python
async def test_file_uploads_increments_on_success(db, application, mock_minio):
    before = REGISTRY.get_sample_value(
        "file_uploads_total_total", {"file_type": "pdf", "status": "success"}
    ) or 0
    await application_service.upload_application_file_minio(app_id, user, fake_file, "pdf")
    after = REGISTRY.get_sample_value(
        "file_uploads_total_total", {"file_type": "pdf", "status": "success"}
    ) or 0
    assert after == before + 1
```

**LOC estimate:** ~8 (service) + 18 (tests) = 26 LOC

---

### M8. `db_connections_total` — Delete

**Rationale:** The pool gauge family (`db_pool_size`, `db_pool_checked_out`,
`db_pool_checked_in`, `db_pool_overflow`) already exposes connection pool state via
`update_db_pool_metrics()`. A monotonic counter of total connections created provides
negligible additional signal. Instrumenting it requires hooking the pool `connect` event
(SQLAlchemy fires it per physical connection, not per checkout), which overlaps awkwardly
with the gauge update approach.

**Action:** Remove `db_connections_total` from `metrics.py` and from `__all__`.

---

### M9. `payment_rosters_total` — Defer to Phase 4

**Rationale:** Roster generation is a low-frequency admin operation. No Grafana panel
currently queries it. The `generate_roster()` method in `roster_service.py` is synchronous
(line 40) and uses the sync session — it can be instrumented trivially when a roster
dashboard is scoped. Adding it now creates test overhead with no observability payoff.

**Action:** Leave counter defined in `metrics.py` (keeps the definition visible) but mark
with a `# TODO(phase4): instrument in roster_service.generate_roster()` comment.

---

## Phase 3 PR Breakdown

### PR-A: Dashboard-Critical Instrumentation (do first)

Scope: M1 + M2 + M3

Files changed:
- `backend/app/db/session.py` (+30 LOC)
- `backend/app/core/db_metrics.py` (new, +15 LOC)
- `backend/app/services/application_service.py` (+10 LOC)
- `backend/app/services/email_management_service.py` (+10 LOC)
- `backend/app/tests/test_metrics_db.py` (new, +20 LOC)
- `backend/app/tests/test_metrics_application.py` (new, +25 LOC)
- `backend/app/tests/test_metrics_email.py` (new, +30 LOC)

**Total: ~140 LOC, 7 new tests**
**Size: Medium**

### PR-B: Lower-Priority Instrumentation + Cleanup (can follow or batch with PR-A)

Scope: M4 + M5 + M6 + M7 + delete M8 + defer M9

Files changed:
- `backend/app/services/auth_service.py` (+12 LOC)
- `backend/app/api/v1/endpoints/auth.py` (+8 LOC)
- `backend/app/services/review_service.py` (+10 LOC)
- `backend/app/main.py` (+5 LOC)
- `backend/app/services/application_service.py` (+8 LOC)
- `backend/app/core/metrics.py` (delete `db_connections_total` definition + __all__ entry, add defer comment)
- `backend/app/tests/test_metrics_auth.py` (new, +20 LOC)
- `backend/app/tests/test_metrics_reviews.py` (new, +20 LOC)
- `backend/app/tests/test_metrics_validation.py` (new, +15 LOC)
- `backend/app/tests/test_metrics_uploads.py` (new, +18 LOC)

**Total: ~116 LOC, 8 new tests**
**Size: Medium**

---

## Summary

| Metric | Action | PR | Est. LOC | Tests |
|---|---|---|---|---|
| `db_query_duration_seconds` | Instrument (sync event listener + async helper) | A | 65 | 1 |
| `scholarship_applications_total` | Instrument (submit + status update) | A | 35 | 2 |
| `email_sent_total` | Instrument (success + failed paths) | A | 40 | 2 |
| `auth_attempts_total` | Instrument (password + SSO) | B | 32 | 1 |
| `scholarship_reviews_total` | Instrument (professor + college) | B | 30 | 1 |
| `validation_errors_total` | Instrument (main.py handler) | B | 20 | 1 |
| `file_uploads_total` | Instrument (minio upload wrapper) | B | 26 | 1 |
| `db_connections_total` | Delete (redundant with pool gauges) | B | -8 | 0 |
| `payment_rosters_total` | Defer to Phase 4 (add TODO comment) | B | 2 | 0 |
| **http_errors_total** | **No action — already instrumented in middleware** | — | 0 | 0 |

**Grand total: ~250 LOC across 2 PRs, 9 new test cases**
