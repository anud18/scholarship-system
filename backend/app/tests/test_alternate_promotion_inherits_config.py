"""Pin: when an alternate is promoted to replace a displaced winner, the
promoted CollegeRankingItem inherits the displaced item's allocation_config_id
(not left NULL → otherwise it lands in the whole-period bucket / wrong roster,
spec §8). Verifies the copy directly at the promotion call site."""

import pytest

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ReviewStage
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.alternate_promotion_service import AlternatePromotionService


@pytest.fixture
def promo_setup(db_sync):
    sch = ScholarshipType(code="promo_sch", name="Promo", description="x")
    db_sync.add(sch)
    db_sync.commit()
    db_sync.refresh(sch)

    consumed = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code="PROMO-114",
        config_name="Promo 114",
        academic_year=114,
        semester=None,
        amount=50000,
    )
    db_sync.add(consumed)
    db_sync.commit()
    db_sync.refresh(consumed)

    requesting = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code="PROMO-115",
        config_name="Promo 115",
        academic_year=115,
        semester=None,
        amount=50000,
    )
    db_sync.add(requesting)
    db_sync.commit()
    db_sync.refresh(requesting)

    def _user(suffix):
        return User(
            nycu_id=f"promo_{suffix}",
            email=f"promo_{suffix}@u.edu",
            name=suffix,
            role=UserRole.student,
            user_type=UserType.student,
        )

    u_orig = _user("orig")
    u_alt = _user("alt")
    db_sync.add_all([u_orig, u_alt])
    db_sync.commit()
    db_sync.refresh(u_orig)
    db_sync.refresh(u_alt)

    def _app(user, app_id):
        return Application(
            app_id=app_id,
            user_id=user.id,
            scholarship_type_id=sch.id,
            scholarship_configuration_id=requesting.id,
            scholarship_subtype_list=["nstc"],
            sub_type_selection_mode=SubTypeSelectionMode.single,
            sub_scholarship_type="nstc",
            academic_year=115,
            semester=None,
            status=ApplicationStatus.approved,
            review_stage=ReviewStage.quota_distributed,
            agree_terms=True,
            student_data={"std_stdcode": app_id, "std_cname": "x"},
        )

    orig_app = _app(u_orig, "APP-PROMO-ORIG")
    alt_app = _app(u_alt, "APP-PROMO-ALT")
    db_sync.add_all([orig_app, alt_app])
    db_sync.commit()
    db_sync.refresh(orig_app)
    db_sync.refresh(alt_app)

    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="nstc",
        academic_year=115,
        semester=None,
        ranking_name="R",
        is_finalized=True,
        ranking_status="finalized",
    )
    db_sync.add(ranking)
    db_sync.commit()
    db_sync.refresh(ranking)

    orig_item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=orig_app.id,
        rank_position=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=consumed.id,
        status="allocated",
        backup_allocations=[{"sub_type": "nstc", "backup_position": 1, "college": "EE"}],
    )
    alt_item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=alt_app.id,
        rank_position=2,
        is_allocated=False,
        backup_position=1,
        status="waitlisted",
        backup_allocations=[{"sub_type": "nstc", "backup_position": 1, "college": "EE"}],
    )
    db_sync.add_all([orig_item, alt_item])
    db_sync.commit()
    db_sync.refresh(orig_item)
    db_sync.refresh(alt_item)
    return {
        "consumed": consumed,
        "requesting": requesting,
        "orig_item": orig_item,
        "alt_item": alt_item,
        "orig_app": orig_app,
    }


def test_promoted_alternate_inherits_allocation_config_id(db_sync, promo_setup):
    svc = AlternatePromotionService(db_sync)
    result = svc.find_and_promote_alternate(
        ranking_item=promo_setup["orig_item"],
        original_application=promo_setup["orig_app"],
        scholarship_config=promo_setup["requesting"],
        ineligible_reason="graduated",
        skip_eligibility_check=True,
    )
    assert result is not None
    db_sync.refresh(promo_setup["alt_item"])
    assert promo_setup["alt_item"].is_allocated is True
    assert promo_setup["alt_item"].allocated_sub_type == "nstc"
    # The promoted alternate consumes the SAME config as the displaced winner.
    assert promo_setup["alt_item"].allocation_config_id == promo_setup["consumed"].id
