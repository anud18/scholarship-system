"""
Pure-function tests for `DeveloperProfileService` + `DeveloperProfileManager`.

DeveloperProfileService is the dev-environment helper that creates
test user accounts on demand. The pure helpers under test build the
DeveloperProfile shape — getting these wrong would propagate wrong
roles / display names into the test suite.

11 cases across 3 helpers:
- `get_default_test_profiles`: deterministic 3-profile suite (student,
  professor, admin) keyed off developer_id.
- `DeveloperProfileManager.create_custom_profile`: pass-through builder
  with optional fields + **custom_attributes kwargs.
- `DeveloperProfileManager.create_student_profiles`: undergraduate
  variety pack.
"""

import pytest

from app.models.user import UserRole
from app.services.developer_profile_service import (
    DeveloperProfile,
    DeveloperProfileManager,
    DeveloperProfileService,
)

# ─── get_default_test_profiles ──────────────────────────────────────


@pytest.fixture
def service():
    return DeveloperProfileService(db=None)  # type: ignore[arg-type]


def test_default_test_profiles_returns_three(service):
    """Default suite: student, professor, admin — exactly 3 profiles."""
    profiles = service.get_default_test_profiles("alice")
    assert len(profiles) == 3


def test_default_test_profiles_roles_are_student_professor_admin(service):
    profiles = service.get_default_test_profiles("alice")
    roles = [p.role for p in profiles]
    assert roles == [UserRole.student, UserRole.professor, UserRole.admin]


def test_default_test_profiles_use_developer_id_in_names(service):
    """The developer_id is interpolated into display names — verify it
    survives across all three profiles (title-cased for English,
    raw for Chinese)."""
    profiles = service.get_default_test_profiles("bob")
    # Student profile.
    assert "Bob" in profiles[0].name
    assert "bob" in profiles[0].chinese_name
    # Professor profile.
    assert "Bob" in profiles[1].name
    assert "Professor Bob" in profiles[1].english_name
    # Admin profile.
    assert "Bob" in profiles[2].name


def test_default_test_profiles_carry_role_specific_attributes(service):
    """Each profile in the default suite has role-appropriate custom_attributes."""
    profiles = service.get_default_test_profiles("charlie")
    # Student gets gpa + year.
    assert profiles[0].custom_attributes.get("gpa") == 3.5
    assert profiles[0].custom_attributes.get("year") == "sophomore"
    # Professor gets department.
    assert profiles[1].custom_attributes.get("department") == "Computer Science"
    # Admin gets permissions.
    assert profiles[2].custom_attributes.get("permissions") == ["full_access"]


# ─── DeveloperProfileManager.create_custom_profile ──────────────────


def test_create_custom_profile_returns_developer_profile_with_required_fields():
    profile = DeveloperProfileManager.create_custom_profile(
        developer_id="dave",
        role=UserRole.student,
        name="Dave Test",
    )
    assert isinstance(profile, DeveloperProfile)
    assert profile.developer_id == "dave"
    assert profile.role == UserRole.student
    assert profile.name == "Dave Test"


def test_create_custom_profile_optional_chinese_english_names_default_to_none():
    profile = DeveloperProfileManager.create_custom_profile(
        developer_id="eve",
        role=UserRole.admin,
        name="Eve Admin",
    )
    assert profile.chinese_name is None
    assert profile.english_name is None


def test_create_custom_profile_passes_chinese_and_english_names():
    profile = DeveloperProfileManager.create_custom_profile(
        developer_id="frank",
        role=UserRole.professor,
        name="Frank",
        chinese_name="法蘭克",
        english_name="Professor Frank",
    )
    assert profile.chinese_name == "法蘭克"
    assert profile.english_name == "Professor Frank"


def test_create_custom_profile_kwargs_flow_into_custom_attributes():
    """Arbitrary **kwargs collect into the custom_attributes dict —
    the dynamic-attributes extension point."""
    profile = DeveloperProfileManager.create_custom_profile(
        developer_id="gina",
        role=UserRole.student,
        name="Gina",
        gpa=3.9,
        year="senior",
        major="CS",
    )
    assert profile.custom_attributes == {"gpa": 3.9, "year": "senior", "major": "CS"}


# ─── DeveloperProfileManager.create_student_profiles ────────────────


def test_create_student_profiles_returns_multiple_undergraduate_variants():
    """The variety pack is at least 2 entries (freshman + others) —
    enough to test multi-year flows."""
    profiles = DeveloperProfileManager.create_student_profiles("henry")
    assert len(profiles) >= 2
    # All profiles are students.
    for p in profiles:
        assert p.role == UserRole.student


def test_create_student_profiles_first_entry_is_freshman():
    """The first profile in the list is the freshman variant."""
    profiles = DeveloperProfileManager.create_student_profiles("isaac")
    first = profiles[0]
    assert "Freshman" in first.name
    assert first.custom_attributes.get("year") == "freshman"
    assert first.custom_attributes.get("student_type") == "undergraduate"


def test_create_student_profiles_all_use_developer_id_in_names():
    profiles = DeveloperProfileManager.create_student_profiles("jane")
    for p in profiles:
        # Either the title-cased English name or the lowercase Chinese
        # name should contain the developer_id token.
        joined = f"{p.name} {p.chinese_name or ''} {p.english_name or ''}"
        assert "jane" in joined.lower()
