"""Pin: the apply-flow visibility sets partition every ApplicationStatus value.

These three sets decide whether a scholarship is shown in the student apply
flow. They MUST stay a partition of the full enum so a newly-added status is
forced into a deliberate classification (and never silently both-shown-and-hidden).
"""

from app.models.enums import (
    ApplicationStatus,
    EDITABLE_APPLICATION_STATUSES,
    HIDDEN_APPLICATION_STATUSES,
    REAPPLY_ALLOWED_APPLICATION_STATUSES,
)


def test_sets_are_value_strings():
    all_values = {s.value for s in ApplicationStatus}
    for bucket in (
        REAPPLY_ALLOWED_APPLICATION_STATUSES,
        EDITABLE_APPLICATION_STATUSES,
        HIDDEN_APPLICATION_STATUSES,
    ):
        assert set(bucket) <= all_values


def test_sets_partition_the_enum():
    reapply = set(REAPPLY_ALLOWED_APPLICATION_STATUSES)
    editable = set(EDITABLE_APPLICATION_STATUSES)
    hidden = set(HIDDEN_APPLICATION_STATUSES)

    # disjoint
    assert reapply & editable == set()
    assert reapply & hidden == set()
    assert editable & hidden == set()

    # cover every enum value
    assert reapply | editable | hidden == {s.value for s in ApplicationStatus}


def test_hidden_set_is_exactly_the_submitted_and_beyond_statuses():
    assert set(HIDDEN_APPLICATION_STATUSES) == {
        "submitted",
        "under_review",
        "pending_documents",
        "approved",
        "partial_approved",
        "manual_excluded",
        "cancelled_by_challenge",
    }
