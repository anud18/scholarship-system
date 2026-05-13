"""
Unit tests for `ApplicationService.get_available_professors`.

Pins the contract for the professor-picker used by the assign-professor
UI (called from `professor.py` endpoints + admin assignment flows).

Behavior under test:
- Returns only users with role=professor (students/college/admin filtered out).
- College admin caller is scoped to their own dept_code; admin/super_admin
  callers see all.
- Search filter matches against both `name` (ilike) and `nycu_id` (ilike).
- Result is ordered by name for stable UI.
- Result rows expose the public-facing fields only
  (nycu_id, name, dept_code, dept_name, email).

These were previously uncovered methods on a 3119-LOC service file —
adding them moves the needle on the production-readiness audit.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService


async def _seed_user(
    db: AsyncSession,
    *,
    role: UserRole,
    name: str,
    nycu_id: str,
    dept_code: str | None = None,
    dept_name: str | None = None,
) -> User:
    u = User(
        nycu_id=nycu_id,
        name=name,
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
        dept_code=dept_code,
        dept_name=dept_name,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_admin_sees_all_professors_across_departments(db: AsyncSession):
    """Admin callers are not scoped by dept_code."""
    await _seed_user(db, role=UserRole.professor, name="Prof Alpha", nycu_id="profA", dept_code="CS")
    await _seed_user(db, role=UserRole.professor, name="Prof Beta", nycu_id="profB", dept_code="EE")
    await _seed_user(db, role=UserRole.professor, name="Prof Gamma", nycu_id="profC", dept_code="ME")
    # Decoy non-professors that must NOT appear.
    await _seed_user(db, role=UserRole.student, name="Stu", nycu_id="stu1")
    await _seed_user(db, role=UserRole.college, name="College", nycu_id="col1", dept_code="CS")
    await _seed_user(db, role=UserRole.admin, name="Admin", nycu_id="admin1")

    admin = await _seed_user(db, role=UserRole.admin, name="Caller Admin", nycu_id="caller_admin")
    service = ApplicationService(db)

    result = await service.get_available_professors(admin)

    nycu_ids = [r["nycu_id"] for r in result]
    assert set(nycu_ids) == {
        "profA",
        "profB",
        "profC",
    }, "admin must see professors across all depts; non-professors must be excluded"


@pytest.mark.asyncio
async def test_super_admin_sees_all_professors(db: AsyncSession):
    """super_admin is also unscoped (no dept_code filter)."""
    await _seed_user(db, role=UserRole.professor, name="A", nycu_id="pA", dept_code="CS")
    await _seed_user(db, role=UserRole.professor, name="B", nycu_id="pB", dept_code="EE")

    super_admin = await _seed_user(db, role=UserRole.super_admin, name="Super", nycu_id="super1")
    service = ApplicationService(db)

    result = await service.get_available_professors(super_admin)
    assert {r["nycu_id"] for r in result} == {"pA", "pB"}


@pytest.mark.asyncio
async def test_college_caller_only_sees_same_dept_professors(db: AsyncSession):
    """College admin's view is scoped to their own dept_code."""
    await _seed_user(db, role=UserRole.professor, name="CS Prof", nycu_id="cs_prof", dept_code="CS")
    await _seed_user(db, role=UserRole.professor, name="EE Prof", nycu_id="ee_prof", dept_code="EE")
    await _seed_user(db, role=UserRole.professor, name="No Dept", nycu_id="ndep_prof", dept_code=None)

    college = await _seed_user(db, role=UserRole.college, name="CS Admin", nycu_id="cs_admin", dept_code="CS")
    service = ApplicationService(db)

    result = await service.get_available_professors(college)
    nycu_ids = {r["nycu_id"] for r in result}
    assert nycu_ids == {"cs_prof"}, "college caller sees only their own dept; null/other-dept profs excluded"


@pytest.mark.asyncio
async def test_search_matches_name_or_nycu_id_case_insensitive(db: AsyncSession):
    """The search filter is OR-ed across name + nycu_id, ilike-style."""
    await _seed_user(db, role=UserRole.professor, name="王明 Chen", nycu_id="prof_chen", dept_code="CS")
    await _seed_user(db, role=UserRole.professor, name="Alice Wu", nycu_id="prof_wu", dept_code="CS")
    await _seed_user(db, role=UserRole.professor, name="李 Three", nycu_id="prof_three", dept_code="CS")

    admin = await _seed_user(db, role=UserRole.admin, name="Caller", nycu_id="caller_search")
    service = ApplicationService(db)

    # Match by partial name (case-insensitive)
    r1 = await service.get_available_professors(admin, search="alice")
    assert {r["nycu_id"] for r in r1} == {"prof_wu"}

    # Match by nycu_id substring
    r2 = await service.get_available_professors(admin, search="three")
    assert {r["nycu_id"] for r in r2} == {"prof_three"}

    # CJK substring on name
    r3 = await service.get_available_professors(admin, search="王")
    assert {r["nycu_id"] for r in r3} == {"prof_chen"}

    # No matches
    r4 = await service.get_available_professors(admin, search="nobody_here")
    assert r4 == []


@pytest.mark.asyncio
async def test_results_are_ordered_by_name(db: AsyncSession):
    """Order-by-name keeps the picker stable across calls."""
    await _seed_user(db, role=UserRole.professor, name="Charlie", nycu_id="pC", dept_code="CS")
    await _seed_user(db, role=UserRole.professor, name="Alice", nycu_id="pA", dept_code="CS")
    await _seed_user(db, role=UserRole.professor, name="Bob", nycu_id="pB", dept_code="CS")

    admin = await _seed_user(db, role=UserRole.admin, name="Caller", nycu_id="caller_order")
    service = ApplicationService(db)

    result = await service.get_available_professors(admin)
    names = [r["name"] for r in result]
    assert names == sorted(names), f"results must be ordered by name; got {names}"


@pytest.mark.asyncio
async def test_result_exposes_only_safe_public_fields(db: AsyncSession):
    """Result rows must NOT leak internal fields (id, role, hashed credentials, etc.)."""
    await _seed_user(
        db,
        role=UserRole.professor,
        name="Prof Public",
        nycu_id="prof_public",
        dept_code="CS",
        dept_name="Computer Science",
    )
    admin = await _seed_user(db, role=UserRole.admin, name="Caller", nycu_id="caller_fields")
    service = ApplicationService(db)

    result = await service.get_available_professors(admin)
    assert len(result) == 1
    row = result[0]
    assert set(row.keys()) == {
        "nycu_id",
        "name",
        "dept_code",
        "dept_name",
        "email",
    }, f"unexpected leakage of internal fields: {set(row.keys())}"
    assert row["nycu_id"] == "prof_public"
    assert row["dept_name"] == "Computer Science"


@pytest.mark.asyncio
async def test_empty_result_when_no_professors_exist(db: AsyncSession):
    """Service does not synthesize fallback data per CLAUDE.md §1 — empty input ⇒ empty result."""
    # Only non-professor users.
    await _seed_user(db, role=UserRole.student, name="S", nycu_id="s1")
    await _seed_user(db, role=UserRole.college, name="C", nycu_id="c1", dept_code="CS")
    admin = await _seed_user(db, role=UserRole.admin, name="Caller", nycu_id="caller_empty")
    service = ApplicationService(db)

    result = await service.get_available_professors(admin)
    assert result == []
