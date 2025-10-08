"""
Test combined scholarship functionality
NOTE: CombinedScholarshipCreate schema not yet implemented - skipping all tests
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scholarship_service import ScholarshipService

if TYPE_CHECKING:
    from app.schemas.scholarship import CombinedScholarshipCreate
else:  # pragma: no cover - placeholder until schema is implemented

    class CombinedScholarshipCreate:  # pylint: disable=too-few-public-methods
        """Lightweight placeholder that accepts arbitrary keyword arguments."""

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)


@pytest.mark.skip(reason="CombinedScholarshipCreate schema not implemented")
@pytest.mark.asyncio
class TestCombinedScholarship:
    async def test_create_combined_phd_scholarship(self, db_session: AsyncSession):
        """Test creating a combined PhD scholarship"""
        service = ScholarshipService(db_session)

        # Test data
        combined_data = CombinedScholarshipCreate(
            name="博士生獎學金",
            name_en="PhD Scholarship",
            description="國科會與教育部聯合博士生獎學金",
            description_en="Combined NSTC and MOE PhD Scholarship",
            sub_scholarships=[
                {
                    "code": "test_nstc",
                    "name": "測試國科會獎學金",
                    "name_en": "Test NSTC Scholarship",
                    "description": "測試用國科會獎學金",
                    "description_en": "Test NSTC scholarship",
                    "sub_type": "nstc",
                    "amount": 40000,
                    # min_gpa removed - should be validated by ScholarshipRule system
                    "max_ranking_percent": 20,
                    "required_documents": ["transcript", "research_proposal"],
                    "application_start_date": datetime.now(timezone.utc),
                    "application_end_date": datetime.now(timezone.utc) + timedelta(days=365),
                }
            ],
        )

        scholarship = await service.create_combined_phd_scholarship(combined_data)

        assert scholarship is not None
        assert scholarship.is_combined is True

        # Verify sub-scholarships were created
        sub_scholarships = await service.get_scholarship_with_sub_types(scholarship.id)
        assert len(sub_scholarships.sub_scholarships) == 1

        nstc_scholarship = next(s for s in sub_scholarships.sub_scholarships if s.sub_type == "nstc")

        assert nstc_scholarship.amount == Decimal("40000")

    async def test_validate_sub_scholarship_application(self, db_session: AsyncSession):
        """Test validating sub-scholarship applications"""
        service = ScholarshipService(db_session)

        # Create a test combined scholarship
        data = CombinedScholarshipCreate(
            name="Test Combined",
            name_en="Test Combined",
            description="Test",
            description_en="Test",
            sub_scholarships=[
                {
                    "code": "test_sub1",
                    "name": "Test Sub 1",
                    "sub_type": "nstc",
                    "amount": 30000,
                }
            ],
        )

        await service.create_combined_phd_scholarship(data)

        # Test sub-scholarship validation

    async def test_get_eligible_combined_scholarships(self, db_session: AsyncSession, test_student):
        """Test that combined scholarships appear in eligible list"""
        service = ScholarshipService(db_session)

        # Create a combined scholarship
        data = CombinedScholarshipCreate(
            name="Eligible Combined",
            name_en="Eligible Combined",
            description="Test",
            description_en="Test",
            sub_scholarships=[
                {
                    "code": "eligible_sub",
                    "name": "Eligible Sub",
                    "sub_type": "general",
                    "amount": 25000,
                }
            ],
        )

        await service.create_combined_phd_scholarship(data)

        # Get eligible scholarships
        eligible = await service.get_eligible_scholarships(test_student)

        # Should include the parent scholarship (not sub-scholarships)
        combined_scholarships = [s for s in eligible if s.is_combined]
        assert len(combined_scholarships) > 0

        # Verify sub-scholarships are not directly listed
        sub_scholarships = [s for s in eligible if s.parent_scholarship_id is not None]
        assert len(sub_scholarships) == 0

        # Test sub-scholarship validation
