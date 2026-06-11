"""G19 (#981): manual bank correction must not destroy the student's submission.

manual_review_bank_info overwrites submitted_form_data in place. The first
correction must permanently preserve the student's original bank fields
(meta_data.original_bank_fields), and every correction must record the
prior values it replaced in verification_details — otherwise「學生當時
實際填了什麼」is unanswerable.
"""

import pytest
import pytest_asyncio

from app.models.application import Application
from app.models.enums import ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.bank_verification_service import BankVerificationService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def app_with_bank_fields(db):
    student = User(
        nycu_id="g19stu001",
        name="G19 學生",
        email="g19stu@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    await db.flush()
    stype = ScholarshipType(code="g19_test", name="G19 Test Scholarship")
    db.add(stype)
    await db.flush()
    cfg = ScholarshipConfiguration(
        config_code="G19-CFG",
        config_name="G19 Config",
        is_active=True,
        scholarship_type_id=stype.id,
        academic_year=114,
        amount=1000,
    )
    db.add(cfg)
    await db.flush()

    app_row = Application(
        app_id="APP-G19-001",
        user_id=student.id,
        scholarship_type_id=stype.id,
        scholarship_configuration_id=cfg.id,
        academic_year=114,
        status="submitted",
        review_stage=ReviewStage.student_submitted,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        submitted_form_data={
            "fields": {
                "postal_account": {
                    "field_id": "postal_account",
                    "field_type": "text",
                    "value": "0001234567890123",
                    "required": True,
                },
                "account_holder": {
                    "field_id": "account_holder",
                    "field_type": "text",
                    "value": "王原始",
                    "required": True,
                },
            },
            "documents": [],
        },
    )
    db.add(app_row)
    await db.commit()
    await db.refresh(app_row)
    return app_row


async def test_first_correction_preserves_original_fields(db, app_with_bank_fields):
    svc = BankVerificationService(db)
    await svc.manual_review_bank_info(
        application_id=app_with_bank_fields.id,
        account_number_approved=None,
        account_number_corrected="7000999988887777",
        account_holder_approved=True,
        account_holder_corrected=None,
        review_notes="G19 test correction",
        reviewer_username="g19admin",
    )
    await db.commit()
    await db.refresh(app_with_bank_fields)

    # The live form now carries the corrected value...
    assert app_with_bank_fields.submitted_form_data["fields"]["postal_account"]["value"] == "7000999988887777"
    # ...but the student's original is permanently preserved.
    original = app_with_bank_fields.meta_data["original_bank_fields"]
    assert original["fields"]["postal_account"] == "0001234567890123"
    assert original["fields"]["account_holder"] == "王原始"
    assert original["preserved_at"]
    # (prior_values per correction are recorded in roster items'
    # bank_verification_details — no roster item exists in this fixture, so
    # the meta_data assertions above are the contract here.)


async def test_second_correction_does_not_clobber_original(db, app_with_bank_fields):
    svc = BankVerificationService(db)
    await svc.manual_review_bank_info(
        application_id=app_with_bank_fields.id,
        account_number_approved=None,
        account_number_corrected="1111111111111111",
        account_holder_approved=None,
        account_holder_corrected=None,
        review_notes="first",
        reviewer_username="g19admin",
    )
    await db.commit()
    await svc.manual_review_bank_info(
        application_id=app_with_bank_fields.id,
        account_number_approved=None,
        account_number_corrected="2222222222222222",
        account_holder_approved=None,
        account_holder_corrected=None,
        review_notes="second",
        reviewer_username="g19admin",
    )
    await db.commit()
    await db.refresh(app_with_bank_fields)

    # original = the STUDENT's value, not the first correction.
    assert app_with_bank_fields.meta_data["original_bank_fields"]["fields"]["postal_account"] == "0001234567890123"
    assert app_with_bank_fields.submitted_form_data["fields"]["postal_account"]["value"] == "2222222222222222"
