"""College (學院) access scoping for applications.

Single source of truth for "may this 學院 user touch this application?".

The authoritative pairing is ``User.college_code`` (``app/models/user.py``)
against the academy code inside ``Application.student_data``. That is exactly the
pairing the college review list already filters on in SQL
(``college_review_service.py``), the distribution read filters on in Python
(``college_review/_helpers.py``), the student-preview scope check uses
(``college_review/application_review.py``) and the file proxy enforces
(``endpoints/files.py``) since PR #1222.

Issue #1223 finding A: ``application_service`` lumped ``UserRole.college`` in
with admin/super_admin and applied no filter at all, so College-A staff could
read — and through the update/delete/restore/assign paths, WRITE — any other
college's application by walking ids.

Fail-closed by construction: a college user with no ``college_code`` binding, and
an application with no SIS snapshot (``student_data IS NULL`` — a batch import
created while the SIS API was unreachable), both evaluate to False. Such rows are
already invisible to college users on every list surface, so denying the
read-by-id keeps the surfaces consistent rather than leaving a side channel.
"""

from typing import Any, Optional

from sqlalchemy import or_

from app.models.application import Application
from app.models.user import User
from app.utils.application_helpers import get_college_code_from_data

# Key precedence MUST stay in lock-step with get_college_code_from_data(). A
# split here is the classic list-vs-detail divergence: an application carrying
# its code under a fallback key would be readable by id but missing from the
# list, or vice versa.
COLLEGE_CODE_KEYS = ("std_academyno", "academy_code", "college_code", "std_college")


def get_user_college_code(user: User) -> str:
    """The user's bound college code, normalized ("" when unbound)."""
    return (getattr(user, "college_code", None) or "").strip()


def get_application_college_code(application: Application) -> str:
    """The applicant's academy code from the SIS snapshot ("" when absent)."""
    return (get_college_code_from_data(application.student_data or {}) or "").strip()


def college_user_may_access(user: User, application: Application) -> bool:
    """True only when a *bound* college user matches the application's academy.

    Both sides must be non-empty: a blank code is not a valid college and must
    never satisfy the comparison (the same defensive rule as
    ``college_review/_helpers.assert_can_manage_ranking``).
    """
    user_college = get_user_college_code(user)
    return bool(user_college) and user_college == get_application_college_code(application)


def college_scope_filter(college_code: str) -> Any:
    """SQL predicate scoping an ``Application`` query to one college.

    ``student_data[key].as_string()`` compiles to ``student_data ->> 'key'`` on
    PostgreSQL and to ``JSON_EXTRACT(...)`` on SQLite, so the same predicate runs
    in production *and* in the aiosqlite test suite.
    (``sa_func.json_extract_path_text``, used by ``college_review_service``, is
    PostgreSQL-only and would blow up the test DB.) Only ``std_pid`` is encrypted
    in ``StudentDataJSON``, so these keys are plaintext and comparable in SQL.

    Mirrors :func:`college_user_may_access` across the full key precedence.
    """
    return or_(*(Application.student_data[key].as_string() == college_code for key in COLLEGE_CODE_KEYS))


def college_scope_for_user(user: User) -> Optional[Any]:
    """SQL predicate for ``user``, or ``None`` when the user is unbound.

    ``None`` means "this college account is bound to nothing" — callers must
    return an EMPTY result, never an unfiltered one.
    """
    college_code = get_user_college_code(user)
    if not college_code:
        return None
    return college_scope_filter(college_code)
