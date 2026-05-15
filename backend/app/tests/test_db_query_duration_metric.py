"""
Counter/histogram-contract tests for db_query_duration_seconds
instrumentation (issue #159, final business-metric counter).

The SQLAlchemy event listeners that observe the histogram are wired in
app.db.session and exercised by every real query in the existing test
suite — so we don't need a dedicated end-to-end test here. These tests
pin:

1. The histogram symbol is importable and recognises the operation
   labels the listener emits.
2. The _classify_operation helper maps SQL verbs to the bounded label
   set the dashboard expects.
"""

from prometheus_client import REGISTRY

from app.core.metrics import db_query_duration_seconds
from app.db.session import _classify_operation


def _bucket_count(operation: str) -> float:
    value = REGISTRY.get_sample_value(
        "db_query_duration_seconds_count",
        labels={"operation": operation},
    )
    return value or 0.0


class TestClassifyOperation:
    def test_select_keyword(self):
        assert _classify_operation("SELECT * FROM users") == "select"

    def test_insert_keyword(self):
        assert _classify_operation("INSERT INTO users (id) VALUES (1)") == "insert"

    def test_update_keyword(self):
        assert _classify_operation("UPDATE users SET name = 'x'") == "update"

    def test_delete_keyword(self):
        assert _classify_operation("DELETE FROM users") == "delete"

    def test_lowercase_normalised(self):
        assert _classify_operation("select 1") == "select"

    def test_leading_whitespace_skipped(self):
        assert _classify_operation("   \n  SELECT 1") == "select"

    def test_unknown_verb_falls_through_to_other(self):
        # BEGIN / COMMIT / VACUUM etc. should not blow up the label
        # cardinality — they all collapse to "other".
        assert _classify_operation("BEGIN") == "other"
        assert _classify_operation("COMMIT") == "other"
        assert _classify_operation("VACUUM ANALYZE users") == "other"

    def test_empty_string_returns_other(self):
        assert _classify_operation("") == "other"

    def test_none_returns_other(self):
        # The listener guards against this in production; verify the
        # helper degrades gracefully if a stray empty value is passed.
        assert _classify_operation(None) == "other"  # type: ignore[arg-type]


class TestDbQueryDurationHistogram:
    def test_observe_increments_select_bucket_count(self):
        before = _bucket_count("select")
        db_query_duration_seconds.labels(operation="select").observe(0.001)
        assert _bucket_count("select") - before == 1.0

    def test_observe_increments_other_bucket_count(self):
        before = _bucket_count("other")
        db_query_duration_seconds.labels(operation="other").observe(0.005)
        assert _bucket_count("other") - before == 1.0

    def test_select_and_insert_label_dimensions_segregate(self):
        before_select = _bucket_count("select")
        before_insert = _bucket_count("insert")
        db_query_duration_seconds.labels(operation="insert").observe(0.002)
        assert _bucket_count("select") - before_select == 0.0
        assert _bucket_count("insert") - before_insert == 1.0
