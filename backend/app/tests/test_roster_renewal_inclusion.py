"""Approved renewals are invisible to the matrix-distribution roster path
because they never win a CollegeRankingItem (renewals are excluded from
allocation). generate_rosters_from_distribution must still surface them:
pull approved renewals directly, group them by
(allocation_config_id, sub_scholarship_type), and produce a roster even when
the group has ONLY renewals (no allocated ranking items)."""

import pytest
from sqlalchemy.dialects import postgresql

from app.models.application import Application, ApplicationStatus
from app.models.enums import ReviewStage
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService


def _mk_common(db_sync):
    st = ScholarshipType(
        name="PhD",
        code="phd",
        description="x",
        sub_type_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
    )
    db_sync.add(st)
    db_sync.flush()
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        academic_year=114,
        semester=None,
        config_name="phd-114",
        config_code="phd_114",
        amount=40000,
    )
    db_sync.add(cfg)
    db_sync.flush()
    user = User(
        nycu_id="413271002",
        email="413271002@nycu.edu.tw",
        name="曾美麗",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db_sync.add(user)
    db_sync.flush()
    return st, cfg, user


@pytest.mark.integration
def test_application_semester_filter_emits_no_invalid_enum_literal(db_sync):
    """Regression: Application.semester is a native Postgres enum
    {first, second, yearly}. The yearly-bucket filter must NOT emit the
    non-existent value 'annual' — SQLite silently tolerates it (so the suite
    passed), but Postgres aborts the whole query with
    `invalid input value for enum semester: "annual"`, breaking every
    yearly-cycle 造冊. Compile to Postgres SQL and assert the literal is gone."""
    service = RosterService(db_sync)
    for sem in ("yearly", "annual", None, ""):
        clause = service._build_application_semester_filter(sem)
        compiled = str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert "annual" not in compiled, f"annual leaked for semester={sem!r}: {compiled}"
        assert "yearly" in compiled


@pytest.mark.integration
def test_renewal_only_generates_roster(db_sync):
    st, cfg, user = _mk_common(db_sync)
    app = Application(
        app_id="APP-114-0-00001R",
        user_id=user.id,
        scholarship_type_id=st.id,
        scholarship_configuration_id=cfg.id,
        allocation_config_id=cfg.id,
        scholarship_name="PhD",
        amount=40000,
        sub_scholarship_type="nstc",
        scholarship_subtype_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        academic_year=114,
        semester=None,
        is_renewal=True,
        renewal_year=114,
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.quota_distributed,
        student_data={"std_stdcode": "413271002", "std_cname": "曾美麗", "std_pid": "A123456789"},
        submitted_form_data={"postal_account": "1234567890123"},
    )
    db_sync.add(app)
    db_sync.commit()

    service = RosterService(db_sync)
    result = service.generate_rosters_from_distribution(
        scholarship_type_id=st.id,
        academic_year=114,
        semester="yearly",
        created_by_user_id=user.id,
        student_verification_enabled=False,
    )

    assert len(result.created) == 1
    roster = result.created[0]
    assert roster.sub_type == "nstc"
    assert roster.total_applications == 1
    item = roster.items[0]
    assert item.application_identity == "114續領"
    assert item.allocated_sub_type == "nstc"
