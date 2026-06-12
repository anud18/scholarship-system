"""G6/G7 (#968/#969): re-reviews must preserve the prior version.

Re-review overwrites ApplicationReview in place and hard-deletes the old
ApplicationReviewItems — the durable version history is the audit row written
by ReviewService._audit_review_revision (old_values = full prior review incl.
per-sub-type decisions). And when a re-review approves everything,
decision_reason gains an explicit 同意 closing line so stale rejection text
no longer reads as the current decision (G7).
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.application import Application
from app.models.audit_log import AuditAction, AuditLog
from app.models.enums import ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.review_service import ReviewService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def review_fixture(db):
    professor = User(
        nycu_id="g6prof",
        name="G6 教授",
        email="g6prof@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.professor,
    )
    student = User(
        nycu_id="g6stu001",
        name="G6 學生",
        email="g6stu@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add_all([professor, student])
    await db.flush()
    stype = ScholarshipType(code="g6_test", name="G6 Test Scholarship", sub_type_list=["nstc", "moe_1w"])
    db.add(stype)
    await db.flush()
    cfg = ScholarshipConfiguration(
        config_code="G6-CFG",
        config_name="G6 Config",
        is_active=True,
        scholarship_type_id=stype.id,
        academic_year=114,
        amount=1000,
    )
    db.add(cfg)
    await db.flush()
    app_row = Application(
        app_id="APP-G6-001",
        user_id=student.id,
        scholarship_type_id=stype.id,
        scholarship_configuration_id=cfg.id,
        academic_year=114,
        status="under_review",
        review_stage=ReviewStage.professor_review,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
    )
    db.add(app_row)
    await db.commit()
    await db.refresh(app_row)
    return {"professor": professor, "app": app_row}


async def _revision_rows(db, review_id: int):
    res = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.resource_type == "application_review",
            AuditLog.resource_id == str(review_id),
        )
        .order_by(AuditLog.id)
    )
    return res.scalars().all()


async def test_re_review_preserves_prior_version_in_audit(db, review_fixture):
    svc = ReviewService(db)
    review = await svc.create_review(
        application_id=review_fixture["app"].id,
        reviewer_id=review_fixture["professor"].id,
        items=[{"sub_type_code": "nstc", "recommendation": "reject", "comments": "資料不齊"}],
    )
    await db.commit()
    review_id = review.id

    # Re-review (the upsert path): same reviewer, now approves.
    await svc.create_review(
        application_id=review_fixture["app"].id,
        reviewer_id=review_fixture["professor"].id,
        items=[{"sub_type_code": "nstc", "recommendation": "approve", "comments": "已補件"}],
    )
    await db.commit()

    rows = await _revision_rows(db, review_id)
    assert len(rows) == 2, "create + revision rows must both exist"
    create_row, revision_row = rows

    assert create_row.action == AuditAction.create.value
    assert create_row.old_values is None
    assert create_row.new_values["items"][0]["recommendation"] == "reject"

    assert revision_row.action == AuditAction.update.value
    # The PRIOR version (the professor's original reject) is reconstructable.
    assert revision_row.old_values["recommendation"] == "reject"
    assert revision_row.old_values["items"][0]["comments"] == "資料不齊"
    assert revision_row.new_values["items"][0]["recommendation"] == "approve"
    assert revision_row.user_id == review_fixture["professor"].id


async def test_approve_after_reject_appends_closing_line(db, review_fixture):
    svc = ReviewService(db)
    await svc.create_review(
        application_id=review_fixture["app"].id,
        reviewer_id=review_fixture["professor"].id,
        items=[{"sub_type_code": "nstc", "recommendation": "reject", "comments": "資料不齊"}],
    )
    # Mirror the submit flow: decision_reason accumulates rejections.
    professor = review_fixture["professor"]
    app_row = review_fixture["app"]
    from datetime import datetime, timezone

    await svc.update_decision_reason(
        app_row,
        professor,
        [{"sub_type_code": "nstc", "recommendation": "reject", "comments": "資料不齊"}],
        datetime.now(timezone.utc),
    )
    await db.commit()
    await db.refresh(app_row)
    assert "資料不齊" in (app_row.decision_reason or "")

    # Re-review approves everything → an explicit closing line is appended.
    await svc.update_decision_reason(
        app_row,
        professor,
        [{"sub_type_code": "nstc", "recommendation": "approve", "comments": "已補件"}],
        datetime.now(timezone.utc),
    )
    await db.commit()
    await db.refresh(app_row)
    assert "重新審核後同意" in app_row.decision_reason
    # Prior rejection text is retained ABOVE the closing line (audit narrative).
    assert app_row.decision_reason.index("資料不齊") < app_row.decision_reason.index("重新審核後同意")
