"""
Counter-contract test for payment_rosters_total instrumentation in
RosterService (issue #159).

Verifies that the counter symbol responds to .inc() with the labels
the service emits ("processing" at creation, "completed" at finalize).
"""

from prometheus_client import REGISTRY

from app.core.metrics import payment_rosters_total


def _sample(status: str) -> float:
    value = REGISTRY.get_sample_value(
        "payment_rosters_total_total",
        labels={"status": status},
    )
    return value or 0.0


class TestPaymentRostersCounter:
    def test_processing_label_increments(self):
        before = _sample("processing")
        payment_rosters_total.labels(status="processing").inc()
        assert _sample("processing") - before == 1.0

    def test_completed_label_increments(self):
        before = _sample("completed")
        payment_rosters_total.labels(status="completed").inc()
        assert _sample("completed") - before == 1.0

    def test_processing_and_completed_segregate(self):
        before_proc = _sample("processing")
        before_done = _sample("completed")
        payment_rosters_total.labels(status="processing").inc()
        assert _sample("processing") - before_proc == 1.0
        assert _sample("completed") - before_done == 0.0
