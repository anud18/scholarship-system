"""
Integration tests for the imperative shared-quota link validation helper
(`_validate_shared_quota_sources`) used by the config create/update endpoints.

Per spec §10 each `source_config_code` must:
  - resolve to an EXISTING config,
  - have `academic_year < this.academic_year` (prior years only),
  - define every listed sub_type (sub_types ⊆ source config's quotas keys).

There is no DB FK on source_config_code, so this is the only gate. A bad
link saved here would later read an empty/missing pool at distribution time.
"""

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.scholarship_configurations import _validate_shared_quota_sources
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipStatus, ScholarshipType


@pytest_asyncio.fixture
async def phd_type(db: AsyncSession) -> ScholarshipType:
    st = ScholarshipType(
        code="link_phd",
        name="Link PhD",
        status=ScholarshipStatus.active.value,
    )
    db.add(st)
    await db.commit()
    await db.refresh(st)
    return st


@pytest_asyncio.fixture
async def phd_113(db: AsyncSession, phd_type) -> ScholarshipConfiguration:
    cfg = ScholarshipConfiguration(
        scholarship_type_id=phd_type.id,
        academic_year=113,
        semester=None,
        config_name="PhD 113",
        config_code="phd_113",
        amount=40000,
        has_college_quota=True,
        quotas={"nstc": {"EE": 5}, "moe_1w": {"EE": 3}},
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def test_valid_link_passes(db: AsyncSession, phd_113):
    sources = [{"source_config_code": "phd_113", "sub_types": ["nstc"]}]
    # academic_year 115 > 113, phd_113 defines nstc -> no raise
    await _validate_shared_quota_sources(db, sources, requesting_academic_year=115)


async def test_missing_target_config_rejected(db: AsyncSession, phd_113):
    sources = [{"source_config_code": "phd_999", "sub_types": ["nstc"]}]
    with pytest.raises(HTTPException) as exc:
        await _validate_shared_quota_sources(db, sources, requesting_academic_year=115)
    assert exc.value.status_code == 400
    assert "phd_999" in exc.value.detail


async def test_non_prior_year_rejected(db: AsyncSession, phd_113):
    sources = [{"source_config_code": "phd_113", "sub_types": ["nstc"]}]
    # requesting year == source year (113) -> not strictly prior -> reject
    with pytest.raises(HTTPException) as exc:
        await _validate_shared_quota_sources(db, sources, requesting_academic_year=113)
    assert exc.value.status_code == 400
    assert "學年度" in exc.value.detail


async def test_undefined_sub_type_rejected(db: AsyncSession, phd_113):
    sources = [{"source_config_code": "phd_113", "sub_types": ["does_not_exist"]}]
    with pytest.raises(HTTPException) as exc:
        await _validate_shared_quota_sources(db, sources, requesting_academic_year=115)
    assert exc.value.status_code == 400
    assert "does_not_exist" in exc.value.detail


async def test_none_and_empty_are_noops(db: AsyncSession):
    # both must return without error and without a DB hit
    await _validate_shared_quota_sources(db, None, requesting_academic_year=115)
    await _validate_shared_quota_sources(db, [], requesting_academic_year=115)
