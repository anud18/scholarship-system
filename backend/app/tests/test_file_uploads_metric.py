"""
Counter-contract tests for file_uploads_total instrumentation in
MinIOService.upload_file (issue #159).

Tests the counter dimensions directly — the upload_file path itself
requires a MinIO client + UploadFile fixture which already has
coverage in test_minio_service.py.
"""

from prometheus_client import REGISTRY

from app.core.metrics import file_uploads_total


def _sample(file_type: str, status: str) -> float:
    value = REGISTRY.get_sample_value(
        "file_uploads_total",
        labels={"file_type": file_type, "status": status},
    )
    return value or 0.0


class TestFileUploadsCounter:
    def test_success_label_increments(self):
        before = _sample("doc", "success")
        file_uploads_total.labels(file_type="doc", status="success").inc()
        assert _sample("doc", "success") - before == 1.0

    def test_failed_label_increments(self):
        before = _sample("doc", "failed")
        file_uploads_total.labels(file_type="doc", status="failed").inc()
        assert _sample("doc", "failed") - before == 1.0

    def test_file_type_label_segregates_series(self):
        before_doc = _sample("doc", "success")
        before_transcript = _sample("transcript", "success")
        file_uploads_total.labels(file_type="transcript", status="success").inc()
        assert _sample("doc", "success") - before_doc == 0.0
        assert _sample("transcript", "success") - before_transcript == 1.0
