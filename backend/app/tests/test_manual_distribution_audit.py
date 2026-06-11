"""G3/G22 (#965/#984): manual allocation must leave an application-level audit trail.

allocate()/finalize() change who receives scholarship money, but previously
wrote only the undo-oriented ManualDistributionHistory snapshot — the formal
audit trail had no record of 「誰在何時把哪個名額配給哪位學生」, and the
history rows never recorded WHO performed the operation (created_by was
always NULL).
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.application import Application, ApplicationStatus
from app.models.audit_log import AuditAction, AuditLog
from app.models.college_review import CollegeRanking, CollegeRankingItem, ManualDistributionHistory
from app.models.enums import ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def dist_fixture(db):
    admin = User(
        nycu_id="g3admin",
        name="G3 Admin",
        email="g3admin@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    student = User(
        nycu_id="g3stu001",
        name="G3 學生",
        email="g3stu@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add_all([admin, student])
    await db.flush()

    stype = ScholarshipType(code="g3_test", name="G3 Test Scholarship", sub_type_list=["nstc"])
    db.add(stype)
    await db.flush()
    cfg = ScholarshipConfiguration(
        config_code="G3-CFG",
        config_name="G3 Config",
        is_active=True,
        scholarship_type_id=stype.id,
        academic_year=114,
        amount=10000,
    )
    db.add(cfg)
    await db.flush()

    app_row = Application(
        app_id="APP-G3-001",
        user_id=student.id,
        scholarship_type_id=stype.id,
        scholarship_configuration_id=cfg.id,
        academic_year=114,
        status=ApplicationStatus.submitted,
        review_stage=ReviewStage.college_ranked,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
    )
    db.add(app_row)
    await db.flush()

    ranking = CollegeRanking(
        scholarship_type_id=stype.id,
        academic_year=114,
        semester=None,
        sub_type_code="nstc",
        created_by=admin.id,
    )
    db.add(ranking)
    await db.flush()

    item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=app_row.id,
        rank_position=1,
        status="ranked",
    )
    db.add(item)
    await db.commit()
    return {"admin": admin, "app": app_row, "item": item, "cfg": cfg, "stype": stype}


async def test_allocate_writes_per_application_audit_and_history_actor(db, dist_fixture):
    svc = ManualDistributionService(db)
    result = await svc.allocate(
        scholarship_type_id=dist_fixture["stype"].id,
        academic_year=114,
        semester="yearly",
        allocations=[
            {
                "ranking_item_id": dist_fixture["item"].id,
                "sub_type_code": "nstc",
                "allocation_config_id": dist_fixture["cfg"].id,
            }
        ],
        admin_user_id=dist_fixture["admin"].id,
    )
    await db.commit()
    assert result["updated_count"] == 1

    rows = (
        (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.resource_type == "application",
                    AuditLog.resource_id == str(dist_fixture["app"].id),
                    AuditLog.action == AuditAction.execute_distribution.value,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1, "allocate must write an application-level audit row (G3)"
    row = rows[0]
    assert row.user_id == dist_fixture["admin"].id
    assert row.old_values["is_allocated"] in (False, None)
    assert row.new_values["allocated_sub_type"] == "nstc"
    assert row.meta_data["ranking_item_id"] == dist_fixture["item"].id

    histories = (
        (await db.execute(select(ManualDistributionHistory).order_by(ManualDistributionHistory.id.desc())))
        .scalars()
        .all()
    )
    assert histories, "allocate should record a history snapshot"
    assert histories[0].created_by == dist_fixture["admin"].id, "history must record WHO acted (G22)"


async def test_allocate_without_actor_writes_no_audit(db, dist_fixture):
    """Back-compat: service callers without an actor (none in production —
    all endpoints pass current_user.id) skip the audit row rather than
    writing one with a bogus user."""
    svc = ManualDistributionService(db)
    await svc.allocate(
        scholarship_type_id=dist_fixture["stype"].id,
        academic_year=114,
        semester="yearly",
        allocations=[
            {
                "ranking_item_id": dist_fixture["item"].id,
                "sub_type_code": "nstc",
                "allocation_config_id": dist_fixture["cfg"].id,
            }
        ],
    )
    await db.commit()
    rows = (
        (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.resource_id == str(dist_fixture["app"].id),
                    AuditLog.action == AuditAction.execute_distribution.value,
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows == []
