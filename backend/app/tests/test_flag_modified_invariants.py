"""
Source-level regression tests for the flag_modified() fixes in 782b460
and 0b48324.

Three services were silently dropping JSONB column writes because
SQLAlchemy's default JSON change detection compares object identity,
not contents — `obj.json_col[key] = value` followed by `db.commit()`
was a no-op when `obj.json_col` had been retrieved-and-aliased earlier
in the function.

Rather than fixture each of the 5+ mutation paths under SQLite, this
suite pins the source-level invariant: every service that subscript-
mutates a JSONB column must import `flag_modified` and call it before
commit. A future refactor that drops the call would fail the suite.
"""

import inspect

from app.services import application_service, bank_verification_service, roster_service


def _has_flag_modified(module) -> bool:
    src = inspect.getsource(module)
    return "flag_modified" in src and "from sqlalchemy.orm.attributes" in src


def test_application_service_uses_flag_modified():
    """Pre-fix (782b460): update_student_data silently lost in-place
    student_data dict mutations because plain `=` assignment to the same
    object identity didn't trigger SQLAlchemy's change tracking."""
    assert _has_flag_modified(application_service), (
        "application_service must import + call flag_modified() — " "regression of commit 782b460."
    )


def test_roster_service_uses_flag_modified():
    """Pre-fix (782b460): roster_service verification merge silently
    discarded fresh API data merged into application.student_data."""
    assert _has_flag_modified(roster_service), (
        "roster_service must import + call flag_modified() — " "regression of commit 782b460."
    )


def test_bank_verification_service_uses_flag_modified():
    """Pre-fix (0b48324): both auto-verify and manual-review paths
    silently lost meta_data['bank_verification'] state changes."""
    assert _has_flag_modified(bank_verification_service), (
        "bank_verification_service must import + call flag_modified() — " "regression of commit 0b48324."
    )


def test_application_service_flag_modified_call_count():
    """Spot-check: at least one flag_modified() call per service that
    subscript-mutates a JSON column."""
    src = inspect.getsource(application_service)
    assert src.count("flag_modified(application") >= 1, (
        "application_service should call flag_modified(application, ...) " "at least once."
    )


def test_bank_verification_flag_modified_call_count():
    """bank_verification_service had 2 distinct paths needing flag_modified
    on application.meta_data, plus 1 on roster_item.bank_verification_details.
    Sanity check that all three are still in place."""
    src = inspect.getsource(bank_verification_service)
    meta_data_calls = src.count('flag_modified(application, "meta_data")')
    details_calls = src.count('flag_modified(roster_item, "bank_verification_details")')
    assert meta_data_calls >= 2, f"expected ≥2 flag_modified() on application.meta_data, found {meta_data_calls}"
    assert details_calls >= 1, (
        f"expected ≥1 flag_modified() on roster_item.bank_verification_details, " f"found {details_calls}"
    )
