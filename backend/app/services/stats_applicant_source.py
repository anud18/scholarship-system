"""The applications the 申請人數 statistics count.

Shared by 統計各學院學生申請人數 and 統計教育部博士生獎學金-各系所獲獎生人數 so
both sheets agree on who an applicant is: the applications the 審核管理 list
shows (everything except draft and deleted) for one scholarship and year.
"""

from typing import Any, List, Mapping, NamedTuple, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.enums import Semester

# Same exclusion as the 審核管理 list (GET /admin/scholarships/{id}/applications).
_EXCLUDED_STATUSES = (ApplicationStatus.draft.value, ApplicationStatus.deleted.value)
# Spellings the distribution loaders accept for a year-based scholarship (stored NULL).
_YEARLY_SEMESTERS = frozenset({"", "yearly", "annual"})


class ApplicantRow(NamedTuple):
    user_id: int
    student_data: Optional[Mapping[str, Any]]
    sub_type_codes: Sequence[str]


async def load_applicant_rows(
    db: AsyncSession,
    *,
    scholarship_type_id: int,
    academic_year: int,
    semester: Optional[str],
    include_renewals: bool = True,
) -> List[ApplicantRow]:
    """Applicants of one scholarship and academic year.

    ``semester`` is ``first`` / ``second`` / ``yearly`` (year-based scholarships
    store NULL or ``yearly``), or None for every semester of the year — callers validate it
    against that set. ``include_renewals=False`` drops 續領 applications, which
    never enter the 甄選. Only the three columns the tallies read are selected
    — skip submitted_form_data & co.
    """
    stmt = select(Application.user_id, Application.student_data, Application.scholarship_subtype_list).where(
        Application.scholarship_type_id == scholarship_type_id,
        Application.academic_year == academic_year,
        Application.deleted_at.is_(None),
        Application.status.notin_(_EXCLUDED_STATUSES),
    )
    if semester is not None:
        normalised = semester.strip().lower()
        if normalised in _YEARLY_SEMESTERS:
            # Year-based applications store NULL or Semester.yearly (creation copies
            # config.semester) — match both, as the ranking scope does.
            stmt = stmt.where(or_(Application.semester.is_(None), Application.semester == Semester.yearly.value))
        else:
            stmt = stmt.where(Application.semester == normalised)
    if not include_renewals:
        stmt = stmt.where(Application.is_renewal.is_(False))
    return [
        ApplicantRow(user_id=user_id, student_data=student_data, sub_type_codes=tuple(sub_types or ()))
        for user_id, student_data, sub_types in (await db.execute(stmt)).all()
    ]
