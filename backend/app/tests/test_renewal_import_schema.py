import pytest
from pydantic import ValidationError

from app.schemas.renewal_import import RenewalDataRow


def test_renewal_row_valid():
    row = RenewalDataRow(
        student_id="413271002",
        student_name="曾美麗",
        sub_type="nstc",
        postal_account="1234567890123",
        advisor_nycu_id="P001234",
    )
    assert row.sub_type == "nstc"
    assert row.postal_account == "1234567890123"


def test_renewal_row_rejects_bad_student_id():
    with pytest.raises(ValidationError):
        RenewalDataRow(student_id="413-271!", student_name="x", sub_type="nstc")


def test_renewal_row_rejects_bad_postal_account():
    with pytest.raises(ValidationError):
        RenewalDataRow(student_id="413271002", student_name="x", sub_type="nstc", postal_account="12ab")
