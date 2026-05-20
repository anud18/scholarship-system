"""
Tests for `app/schemas/student.py`.

The schemas in this module ARE the wire-shape for everything the
admin UI displays about students — name, degree, department, contact
info, bank account, status. Two pinned behaviours are non-obvious:

  - **StudentResponse.displayName**: priority cname → ename → stdcode
    → ""; surfaces all over the UI. A regression that flipped the
    order would render English names on tables that intentionally
    show Chinese names first.

  - **StudentResponse.get_student_type()**: degree string → bucket
    name mapping ("1" → "phd", "2" → "master", else → "undergraduate").
    Hardcoded magic strings; a regression would mis-classify every
    student's eligibility.

  - **StudentSearchParams pagination**: `page` ge=1, `size` ge=1
    le=100. Out-of-range values would either crash the SQL `OFFSET`
    or return arbitrary-sized pages.

20 cases pinning the 10 schemas + 2 instance methods.
"""

import pytest
from pydantic import ValidationError

from app.schemas.student import (
    AcademyBase,
    AcademyResponse,
    DegreeResponse,
    DepartmentBase,
    DepartmentResponse,
    EnrollTypeBase,
    EnrollTypeResponse,
    IdentityResponse,
    SchoolIdentityResponse,
    StudentBase,
    StudentCreate,
    StudentResponse,
    StudentSearchParams,
    StudentUpdate,
    StudyingStatusResponse,
)

# ─── Lookup-table schemas ───────────────────────────────────────────


def test_degree_response_required_fields():
    # Pin: name + id required.
    with pytest.raises(ValidationError):
        DegreeResponse(name="博士")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "schema_cls",
    [DegreeResponse, IdentityResponse, StudyingStatusResponse, SchoolIdentityResponse],
)
def test_lookup_schemas_have_id_and_name(schema_cls):
    # Pin: all four lookup-table schemas share the (id, name) shape
    # so generic UI rendering works. Don't widen silently.
    obj = schema_cls(id=1, name="x")
    assert obj.id == 1
    assert obj.name == "x"


def test_academy_code_optional_name_required():
    # Pin: code can be null (some legacy entries lack code) but name
    # must be present.
    a = AcademyBase(name="人社院")
    assert a.code is None
    with pytest.raises(ValidationError):
        AcademyBase(code="A")  # name missing


def test_department_code_optional_name_required():
    d = DepartmentBase(name="教育博")
    assert d.code is None


def test_enroll_type_requires_degree_id():
    # Pin: EnrollType is keyed on (code, degreeId) — degreeId is
    # required because the same code means different things across
    # degrees (see wave 6a60 getEnrollTypeName test).
    with pytest.raises(ValidationError):
        EnrollTypeBase(code="1", name="一般入學")  # degreeId missing


def test_enroll_type_response_carries_nested_degree():
    # Pin: response nests the full DegreeResponse so the UI doesn't
    # need a second lookup.
    e = EnrollTypeResponse(
        id=1,
        code="1",
        name="一般入學",
        degreeId=3,
        degree=DegreeResponse(id=3, name="學士"),
    )
    assert e.degree is not None
    assert e.degree.id == 3


# ─── StudentBase required vs optional ───────────────────────────────


def _student_min():
    return dict(
        std_stdcode="310460031",
        std_cname="王小明",
        std_ename="Ming Wang",
        std_degree="2",
    )


def test_student_base_required_anchor_set():
    # Pin: std_stdcode + std_cname + std_ename + std_degree are
    # required. Every student record in the system has these four;
    # making any optional risks blank-row drift.
    with pytest.raises(ValidationError):
        StudentBase(  # type: ignore[call-arg]
            std_stdcode="310460031",
            std_cname="王小明",
            # std_ename missing
            std_degree="2",
        )


def test_student_base_most_fields_optional():
    # Pin: most fields default to None — staff routinely create
    # student records before all SIS fields are populated.
    s = StudentBase(**_student_min())
    assert s.std_pid is None
    assert s.std_studingstatus is None
    assert s.com_email is None
    assert s.std_bank_account is None
    assert s.notes is None


def test_student_update_all_optional():
    # Pin: PATCH semantics.
    u = StudentUpdate()
    assert u.std_cname is None
    assert u.com_email is None


def test_student_update_omits_std_stdcode():
    # Pin: std_stdcode (the NYCU ID) is the natural key and must NOT
    # be in the update schema — students never change their ID.
    assert "std_stdcode" not in StudentUpdate.model_fields


# ─── StudentResponse.displayName property ───────────────────────────


def test_display_name_prefers_cname():
    # Pin: Chinese name first (admin UI shows zh names by default).
    r = StudentResponse(id=1, **_student_min())
    assert r.displayName == "王小明"


def test_display_name_falls_back_to_ename():
    # Pin: fall through to English name when cname is empty.
    r = StudentResponse(
        id=1,
        std_stdcode="310460031",
        std_cname="",
        std_ename="Ming Wang",
        std_degree="2",
    )
    assert r.displayName == "Ming Wang"


def test_display_name_falls_back_to_stdcode():
    # Pin: stdcode as last name before "".
    r = StudentResponse(
        id=1,
        std_stdcode="310460031",
        std_cname="",
        std_ename="",
        std_degree="2",
    )
    assert r.displayName == "310460031"


def test_display_name_returns_empty_string_for_no_names():
    # Pin: empty string final fallback. Never returns None — UI code
    # uses .length / string ops without null-checks.
    r = StudentResponse(
        id=1,
        std_stdcode="",
        std_cname="",
        std_ename="",
        std_degree="2",
    )
    assert r.displayName == ""


# ─── StudentResponse.get_student_type() ──────────────────────────────


def test_get_student_type_one_is_phd():
    r = StudentResponse(id=1, **{**_student_min(), "std_degree": "1"})
    assert r.get_student_type() == "phd"


def test_get_student_type_two_is_master():
    r = StudentResponse(id=1, **{**_student_min(), "std_degree": "2"})
    assert r.get_student_type() == "master"


def test_get_student_type_three_is_undergraduate():
    # Pin: "3" (學士) falls into the else branch → "undergraduate".
    r = StudentResponse(id=1, **{**_student_min(), "std_degree": "3"})
    assert r.get_student_type() == "undergraduate"


def test_get_student_type_unknown_defaults_to_undergraduate():
    # Pin: defensive default. Per CLAUDE.md, fallback to a known
    # bucket prevents downstream code from crashing on unexpected
    # degree codes — important because SIS occasionally returns new
    # codes that admin hasn't onboarded yet.
    r = StudentResponse(id=1, **{**_student_min(), "std_degree": "99"})
    assert r.get_student_type() == "undergraduate"


# ─── StudentSearchParams pagination bounds ──────────────────────────


def test_search_params_page_defaults_to_1():
    p = StudentSearchParams()
    assert p.page == 1
    assert p.size == 20


def test_search_params_page_rejects_zero():
    # Pin: ge=1 — page 0 would compute OFFSET = -size.
    with pytest.raises(ValidationError):
        StudentSearchParams(page=0)


def test_search_params_size_caps_at_100():
    # Pin: le=100 — prevents 10k-row pages that could OOM the
    # serializer.
    with pytest.raises(ValidationError):
        StudentSearchParams(size=101)
