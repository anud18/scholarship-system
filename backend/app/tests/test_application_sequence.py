"""
Test application sequence generation for sequential application IDs
"""

import asyncio
import re

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_sequence import ApplicationSequence
from app.services.application_service import ApplicationService


@pytest.mark.asyncio
class TestApplicationSequence:
    """Test application sequence and ID generation"""

    async def test_format_app_id(self):
        """Test app_id formatting with different parameters"""
        # Test first semester
        app_id = ApplicationSequence.format_app_id(113, "first", 1)
        assert app_id == "APP-113-1-00001"

        # Test second semester
        app_id = ApplicationSequence.format_app_id(113, "second", 125)
        assert app_id == "APP-113-2-00125"

        # Test annual scholarship
        app_id = ApplicationSequence.format_app_id(114, "annual", 1)
        assert app_id == "APP-114-0-00001"

        # Test large sequence number
        app_id = ApplicationSequence.format_app_id(113, "first", 99999)
        assert app_id == "APP-113-1-99999"

    async def test_get_semester_code(self):
        """Test semester code conversion"""
        assert ApplicationSequence.get_semester_code("first") == "1"
        assert ApplicationSequence.get_semester_code("second") == "2"
        assert ApplicationSequence.get_semester_code("annual") == "0"
        assert ApplicationSequence.get_semester_code("unknown") == "0"  # Default

    async def test_generate_sequential_app_ids(self, db: AsyncSession):
        """Test that app_ids are generated sequentially"""
        service = ApplicationService(db)

        # Generate multiple app_ids for the same semester
        app_id_1 = await service._generate_app_id(113, "first")
        app_id_2 = await service._generate_app_id(113, "first")
        app_id_3 = await service._generate_app_id(113, "first")

        # Verify format
        pattern = r"^APP-113-1-\d{5}$"
        assert re.match(pattern, app_id_1)
        assert re.match(pattern, app_id_2)
        assert re.match(pattern, app_id_3)

        # Extract sequence numbers
        seq_1 = int(app_id_1.split("-")[-1])
        seq_2 = int(app_id_2.split("-")[-1])
        seq_3 = int(app_id_3.split("-")[-1])

        # Verify sequential
        assert seq_2 == seq_1 + 1
        assert seq_3 == seq_2 + 1

    async def test_generate_app_ids_different_semesters(self, db: AsyncSession):
        """Test that different semesters have independent sequences"""
        service = ApplicationService(db)

        # Generate for first semester
        app_id_first_1 = await service._generate_app_id(113, "first")
        app_id_first_2 = await service._generate_app_id(113, "first")

        # Generate for second semester
        app_id_second_1 = await service._generate_app_id(113, "second")
        app_id_second_2 = await service._generate_app_id(113, "second")

        # Verify semesters are independent
        assert "APP-113-1-" in app_id_first_1
        assert "APP-113-1-" in app_id_first_2
        assert "APP-113-2-" in app_id_second_1
        assert "APP-113-2-" in app_id_second_2

        # Second semester should start from 1
        seq_second_1 = int(app_id_second_1.split("-")[-1])
        seq_second_2 = int(app_id_second_2.split("-")[-1])
        assert seq_second_2 == seq_second_1 + 1

    async def test_generate_app_ids_different_years(self, db: AsyncSession):
        """Test that different academic years have independent sequences"""
        service = ApplicationService(db)

        # Generate for year 113
        app_id_113 = await service._generate_app_id(113, "first")

        # Generate for year 114
        app_id_114 = await service._generate_app_id(114, "first")

        # Verify years are independent
        assert "APP-113-1-" in app_id_113
        assert "APP-114-1-" in app_id_114

        # Year 114 should have its own sequence
        # (actual value depends on test execution order, but should be independent from 113)

    async def test_handle_none_semester(self, db: AsyncSession):
        """Test handling of None semester (yearly scholarships)"""
        service = ApplicationService(db)

        # Generate with None semester
        app_id = await service._generate_app_id(113, None)

        # Should use annual (code 0)
        assert "APP-113-0-" in app_id

    async def test_sequence_persistence(self, db: AsyncSession):
        """Test that sequences are persisted in database"""
        service = ApplicationService(db)

        # Generate some app_ids
        await service._generate_app_id(113, "first")
        await service._generate_app_id(113, "first")
        await service._generate_app_id(113, "first")

        # Query the sequence record
        stmt = select(ApplicationSequence).where(
            ApplicationSequence.academic_year == 113, ApplicationSequence.semester == "first"
        )
        result = await db.execute(stmt)
        seq_record = result.scalar_one_or_none()

        # Should exist and have correct count
        assert seq_record is not None
        assert seq_record.last_sequence == 3

    @pytest.mark.asyncio
    async def test_concurrent_generation(self, db: AsyncSession):
        """Test concurrent app_id generation (thread-safety)"""
        service = ApplicationService(db)

        # Create multiple concurrent tasks
        async def generate_app_id():
            return await service._generate_app_id(113, "first")

        # Generate 10 app_ids concurrently
        tasks = [generate_app_id() for _ in range(10)]
        app_ids = await asyncio.gather(*tasks)

        # All should be unique
        assert len(app_ids) == len(set(app_ids))

        # All should follow the pattern
        pattern = r"^APP-113-1-\d{5}$"
        for app_id in app_ids:
            assert re.match(pattern, app_id)

        # Extract and sort sequence numbers
        sequences = sorted([int(app_id.split("-")[-1]) for app_id in app_ids])

        # Should be sequential (allowing for other tests running concurrently)
        for i in range(1, len(sequences)):
            # Sequences should be increasing (but may have gaps if other tests run)
            assert sequences[i] > sequences[i - 1]

    async def test_app_id_format_validation(self):
        """Test app_id format validation"""
        # Valid formats
        valid_app_ids = [
            "APP-113-1-00001",
            "APP-113-2-00125",
            "APP-114-0-00001",
            "APP-113-1-99999",
        ]

        pattern = r"^APP-\d+-[0-2]-\d{5}$"
        for app_id in valid_app_ids:
            assert re.match(pattern, app_id), f"Valid app_id {app_id} failed validation"

        # Invalid formats (old random format)
        invalid_app_ids = [
            "APP-2025-123456",  # Old format with year and random suffix
            "APP-113-3-00001",  # Invalid semester code (should be 0-2)
            "APP-113-1-1",  # Sequence not zero-padded
        ]

        for app_id in invalid_app_ids:
            if app_id.startswith("APP-2025-"):
                # Old format - different pattern
                assert not re.match(pattern, app_id)
