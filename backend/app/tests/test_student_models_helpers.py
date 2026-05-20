"""
Tests for `backend/app/models/student.py` —
EnrollType.__repr__ + get_student_type_from_degree helper.

Existing tests reference `from app.models.student import ...`
but no DEDICATED tests for the model-level helpers. The
`get_student_type_from_degree` function drives the student-type
mapping used by scholarship-eligibility checks; drift would
silently route PhD students to undergraduate eligibility rules
(or vice versa).

Wave 6a150 pins:
- EnrollType.__repr__ formatting
- get_student_type_from_degree int coercion (string → int)
- ValueError/TypeError fallback to 3 (undergraduate)
- degree.name → "phd"/"master"/"undergraduate" mapping
- not-found fallback to "undergraduate"

Uses unbound-method trick to test __repr__ on SimpleNamespace
(bypasses SQLAlchemy InstrumentedAttribute requirement) and
AsyncMock to mock the DB session.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.models.student import EnrollType, get_student_type_from_degree


class TestEnrollTypeRepr:
    """Pin: EnrollType.__repr__ formatting for debug output."""

    def test_repr_format(self):
        # Pin: f"<EnrollType(id={self.id}, name={self.name}, degree={self.degreeId})>"
        # Pin so refactor doesn't change format (admin debug logs
        # may parse this).
        stand_in = SimpleNamespace(id=42, name="一般生", degreeId=3)
        result = EnrollType.__repr__(stand_in)
        assert result == "<EnrollType(id=42, name=一般生, degree=3)>"

    def test_repr_handles_none_name(self):
        # Pin: handles None name without crashing (uses f-string
        # which calls str(None) → "None").
        stand_in = SimpleNamespace(id=1, name=None, degreeId=1)
        result = EnrollType.__repr__(stand_in)
        assert "name=None" in result


class TestGetStudentTypeFromDegree:
    """Pin: get_student_type_from_degree mapping.

    Maps degree_code (1=博士/2=碩士/3=學士) → English string for
    scholarship-eligibility rules.
    """

    @pytest.mark.asyncio
    async def test_degree_code_1_phd(self):
        # Pin: degree_code "1" (with zh-TW DB row "博士") → "phd".
        session = MagicMock()
        session.execute = AsyncMock()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=SimpleNamespace(name="博士"))

        result = await get_student_type_from_degree("1", session)
        assert result == "phd"

    @pytest.mark.asyncio
    async def test_degree_code_2_master(self):
        session = MagicMock()
        session.execute = AsyncMock()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=SimpleNamespace(name="碩士"))

        result = await get_student_type_from_degree("2", session)
        assert result == "master"

    @pytest.mark.asyncio
    async def test_degree_code_3_undergraduate(self):
        # Pin: 學士 → "undergraduate".
        session = MagicMock()
        session.execute = AsyncMock()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=SimpleNamespace(name="學士"))

        result = await get_student_type_from_degree("3", session)
        assert result == "undergraduate"

    @pytest.mark.asyncio
    async def test_unknown_degree_name_falls_back_to_undergraduate(self):
        # Pin: when degree row exists but name is neither 博士
        # nor 碩士, fall back to "undergraduate". Pin so refactor
        # doesn't introduce silent "unknown" string that breaks
        # downstream eligibility lookup.
        session = MagicMock()
        session.execute = AsyncMock()
        session.execute.return_value.scalar_one_or_none = MagicMock(
            return_value=SimpleNamespace(name="專科")  # Junior college
        )

        result = await get_student_type_from_degree("9", session)
        assert result == "undergraduate"

    @pytest.mark.asyncio
    async def test_degree_not_found_falls_back_to_undergraduate(self):
        # Pin: DB returns None → fallback "undergraduate".
        # Pin SECURITY: refactor changing to raise would crash
        # the eligibility check for unknown degree codes (breaks
        # SIS API onboarding when new degree codes appear).
        session = MagicMock()
        session.execute = AsyncMock()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        result = await get_student_type_from_degree("99", session)
        assert result == "undergraduate"

    @pytest.mark.asyncio
    async def test_invalid_string_falls_back_to_degree_id_3(self):
        # Pin: non-numeric degree_code triggers ValueError →
        # fall back to degree_id=3 (undergraduate). Pin so refactor
        # doesn't propagate the error and crash on bad SIS data.
        session = MagicMock()
        session.execute = AsyncMock()
        # Whatever degree_id=3 returns, it should be queried (NOT raise).
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=SimpleNamespace(name="學士"))

        result = await get_student_type_from_degree("not-a-number", session)
        assert result == "undergraduate"
        # Verify it actually queried (didn't short-circuit)
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_degree_code_falls_back_to_degree_id_3(self):
        # Pin: None / TypeError fallback to 3 (undergraduate).
        # Pin so caller passing None doesn't crash.
        session = MagicMock()
        session.execute = AsyncMock()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=SimpleNamespace(name="學士"))

        result = await get_student_type_from_degree(None, session)
        assert result == "undergraduate"
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_int_coercion_from_numeric_string(self):
        # Pin: "1" string → int(1) coercion → DB query for degree_id=1.
        # Pin so refactor to strict-typing doesn't break the
        # SIS-API integration which sends degree codes as strings.
        session = MagicMock()
        session.execute = AsyncMock()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=SimpleNamespace(name="博士"))

        result = await get_student_type_from_degree("1", session)
        assert result == "phd"


class TestModelTableNames:
    """Pin: __tablename__ for the 8 reference-data models.
    Drift in table names breaks the database schema."""

    def test_degree_tablename(self):
        from app.models.student import Degree

        assert Degree.__tablename__ == "degrees"

    def test_identity_tablename(self):
        from app.models.student import Identity

        assert Identity.__tablename__ == "identities"

    def test_studying_status_tablename(self):
        from app.models.student import StudyingStatus

        assert StudyingStatus.__tablename__ == "studying_statuses"

    def test_school_identity_tablename(self):
        from app.models.student import SchoolIdentity

        assert SchoolIdentity.__tablename__ == "school_identities"

    def test_gender_tablename(self):
        from app.models.student import Gender

        assert Gender.__tablename__ == "genders"

    def test_academy_tablename(self):
        from app.models.student import Academy

        assert Academy.__tablename__ == "academies"

    def test_department_tablename(self):
        from app.models.student import Department

        assert Department.__tablename__ == "departments"

    def test_enroll_type_tablename(self):
        assert EnrollType.__tablename__ == "enroll_types"

    def test_enroll_type_unique_constraint_name(self):
        # Pin: uq_degree_code is the constraint name used by
        # SeedScripts ON CONFLICT clauses. Pin so refactor renaming
        # the constraint silently breaks idempotent seeds.
        constraint_names = []
        for arg in EnrollType.__table_args__:
            if hasattr(arg, "name") and arg.name:
                constraint_names.append(arg.name)
        assert "uq_degree_code" in constraint_names
