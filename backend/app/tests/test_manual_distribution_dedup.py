"""Regression test for get_students_for_distribution's per-application dedup.

When an application appears in two finalized rankings of the same college (e.g. a
"default" ranking finalized alongside a specific sub-type one), allocation state lives
per-ranking-item. The dedup must keep ONE row per application AND prefer the item that
carries the real allocation — otherwise the rank-ordered first (unallocated) item would
hide a persisted allocation. See issue #1034 follow-up.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.manual_distribution_service import ManualDistributionService


def _item(item_id, rank, *, app, is_allocated, allocated_sub_type=None):
    return SimpleNamespace(
        id=item_id,
        rank_position=rank,
        allocated_sub_type=allocated_sub_type,
        allocation_config_id=None,
        is_allocated=is_allocated,
        status="allocated" if is_allocated else "ranked",
        college_rejected=False,
        is_supplementary=False,
        received_months=None,
        received_months_source=None,
        application=app,
    )


async def test_dedup_prefers_allocated_item_over_unallocated_duplicate():
    db = MagicMock()
    # One application (id=100) with TWO ranking items: the rank-1 item is UNallocated,
    # the rank-2 duplicate carries the real allocation.
    app = SimpleNamespace(
        id=100,
        deleted_at=None,
        student_data={"std_academyno": "C", "std_cname": "王某"},
        scholarship_subtype_list=["nstc"],
        quota_allocation_status="allocated",
        revoke_reason=None,
        suspend_reason=None,
        is_renewal=False,
        renewal_year=None,
    )
    unallocated = _item(11, 1, app=app, is_allocated=False)
    allocated = _item(12, 2, app=app, is_allocated=True, allocated_sub_type="nstc")

    ranking = SimpleNamespace(id=5)

    def _execute(stmt, *a, **k):
        result = MagicMock()
        scalars = MagicMock()
        # First execute → finalized rankings; second → ranking items.
        if not getattr(_execute, "called", False):
            _execute.called = True
            scalars.all.return_value = [ranking]
        else:
            scalars.all.return_value = [unallocated, allocated]
        result.scalars.return_value = scalars
        return result

    db.execute = AsyncMock(side_effect=_execute)

    svc = ManualDistributionService(db)
    # Isolate the dedup: stub the per-student/bulk helpers.
    svc._batch_load_rejected_map = AsyncMock(return_value={})
    svc._bulk_system_received_months = AsyncMock(return_value={})
    svc._compute_application_identity = MagicMock(return_value="114新申請")
    svc._compute_term_count = MagicMock(return_value=1)
    svc._format_enrollment_date = MagicMock(return_value="")
    svc._get_renewal_sub_type = MagicMock(return_value=None)

    students = await svc.get_students_for_distribution(2, 114, "yearly")

    assert len(students) == 1, "application appearing in two rankings must yield ONE row"
    row = students[0]
    assert row["is_allocated"] is True, "dedup must surface the allocated item, not hide the allocation"
    assert row["ranking_item_id"] == 12
    assert row["allocated_sub_type"] == "nstc"


async def test_dedup_keeps_single_row_when_no_allocation():
    """Two unallocated duplicates collapse to a single (deterministic) row."""
    db = MagicMock()
    app = SimpleNamespace(
        id=200,
        deleted_at=None,
        student_data={"std_academyno": "E"},
        scholarship_subtype_list=[],
        quota_allocation_status=None,
        revoke_reason=None,
        suspend_reason=None,
        is_renewal=False,
        renewal_year=None,
    )
    i1 = _item(21, 1, app=app, is_allocated=False)
    i2 = _item(22, 2, app=app, is_allocated=False)
    ranking = SimpleNamespace(id=9)

    def _execute(stmt, *a, **k):
        result = MagicMock()
        scalars = MagicMock()
        if not getattr(_execute, "called", False):
            _execute.called = True
            scalars.all.return_value = [ranking]
        else:
            scalars.all.return_value = [i1, i2]
        result.scalars.return_value = scalars
        return result

    db.execute = AsyncMock(side_effect=_execute)
    svc = ManualDistributionService(db)
    svc._batch_load_rejected_map = AsyncMock(return_value={})
    svc._bulk_system_received_months = AsyncMock(return_value={})
    svc._compute_application_identity = MagicMock(return_value="114新申請")
    svc._compute_term_count = MagicMock(return_value=1)
    svc._format_enrollment_date = MagicMock(return_value="")
    svc._get_renewal_sub_type = MagicMock(return_value=None)

    students = await svc.get_students_for_distribution(2, 114, "yearly")

    assert len(students) == 1
    assert students[0]["ranking_item_id"] == 21  # first by (rank_position, id)


async def test_items_query_orders_by_rank_then_id_for_determinism():
    """The items query must ORDER BY (rank_position, id) so the dedup is deterministic
    when an application appears in multiple finalized rankings (asserts the SQL itself,
    since the mock can't enforce ordering)."""
    db = MagicMock()
    captured = []
    ranking = SimpleNamespace(id=1)

    def _execute(stmt, *a, **k):
        captured.append(stmt)
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [ranking] if len(captured) == 1 else []
        result.scalars.return_value = scalars
        return result

    db.execute = AsyncMock(side_effect=_execute)
    svc = ManualDistributionService(db)
    svc._batch_load_rejected_map = AsyncMock(return_value={})
    svc._bulk_system_received_months = AsyncMock(return_value={})

    await svc.get_students_for_distribution(2, 114, "yearly")

    # 2nd executed statement is the ranking-items query.
    items_sql = str(captured[1]).lower()
    assert "order by" in items_sql, f"items query must be ordered; got: {items_sql}"
    order_by = items_sql.split("order by", 1)[1]
    assert "rank_position" in order_by, f"must order by rank_position; got: {order_by}"
    assert "id" in order_by, f"must include an id tiebreak for determinism; got: {order_by}"


async def test_dedup_both_allocated_collapses_to_single_deterministic_row():
    """When BOTH duplicate items are allocated (a data anomaly), the grid can only show
    one — pin the deterministic choice (first by rank_position, id). Documents current
    behavior; a warning is logged for the hidden allocation."""
    db = MagicMock()
    app = SimpleNamespace(
        id=300,
        deleted_at=None,
        student_data={"std_academyno": "C"},
        scholarship_subtype_list=["nstc", "moe_1w"],
        quota_allocation_status="allocated",
        revoke_reason=None,
        suspend_reason=None,
        is_renewal=False,
        renewal_year=None,
    )
    a1 = _item(31, 1, app=app, is_allocated=True, allocated_sub_type="nstc")
    a2 = _item(32, 2, app=app, is_allocated=True, allocated_sub_type="moe_1w")
    ranking = SimpleNamespace(id=7)

    def _execute(stmt, *a, **k):
        result = MagicMock()
        scalars = MagicMock()
        if not getattr(_execute, "called", False):
            _execute.called = True
            scalars.all.return_value = [ranking]
        else:
            scalars.all.return_value = [a1, a2]
        result.scalars.return_value = scalars
        return result

    db.execute = AsyncMock(side_effect=_execute)
    svc = ManualDistributionService(db)
    svc._batch_load_rejected_map = AsyncMock(return_value={})
    svc._bulk_system_received_months = AsyncMock(return_value={})
    svc._compute_application_identity = MagicMock(return_value="114新申請")
    svc._compute_term_count = MagicMock(return_value=1)
    svc._format_enrollment_date = MagicMock(return_value="")
    svc._get_renewal_sub_type = MagicMock(return_value=None)

    students = await svc.get_students_for_distribution(2, 114, "yearly")

    assert len(students) == 1
    assert students[0]["ranking_item_id"] == 31  # first by (rank_position, id)
    assert students[0]["is_allocated"] is True
