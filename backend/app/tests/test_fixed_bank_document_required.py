"""
`ApplicationFieldService.is_fixed_bank_document_required` — the single
source of truth for whether 存摺封面 gates 提交申請.

The built-in document is required and has no row of its own; only an
admin's materialised `bank_statement` row (審核管理 → 系統預設) can relax it,
and a deactivated row relaxes it as well because the student never sees it.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_field import ApplicationDocument
from app.services.application_field_service import FIXED_KEY_BANK_STATEMENT, ApplicationFieldService


async def _materialise(db: AsyncSession, scholarship_type: str, **overrides) -> None:
    db.add(
        ApplicationDocument(
            scholarship_type=scholarship_type,
            fixed_key=FIXED_KEY_BANK_STATEMENT,
            document_name="存摺封面",
            **overrides,
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_required_when_no_row_exists(db: AsyncSession):
    assert await ApplicationFieldService(db).is_fixed_bank_document_required("phd") is True


@pytest.mark.asyncio
async def test_required_when_the_admin_row_keeps_it_required(db: AsyncSession):
    await _materialise(db, "phd_req", is_required=True, is_active=True)

    assert await ApplicationFieldService(db).is_fixed_bank_document_required("phd_req") is True


@pytest.mark.asyncio
async def test_not_required_when_the_admin_row_relaxes_it(db: AsyncSession):
    await _materialise(db, "phd_opt", is_required=False, is_active=True)

    assert await ApplicationFieldService(db).is_fixed_bank_document_required("phd_opt") is False


@pytest.mark.asyncio
async def test_not_required_when_the_admin_row_is_deactivated(db: AsyncSession):
    await _materialise(db, "phd_off", is_required=True, is_active=False)

    assert await ApplicationFieldService(db).is_fixed_bank_document_required("phd_off") is False


@pytest.mark.asyncio
async def test_rows_are_scoped_per_scholarship_type(db: AsyncSession):
    await _materialise(db, "phd_scoped", is_required=False, is_active=True)

    assert await ApplicationFieldService(db).is_fixed_bank_document_required("undergraduate_scoped") is True
