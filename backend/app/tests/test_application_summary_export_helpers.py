"""
Tests for pure helpers in
`app.api.v1.endpoints.college_review.application_summary_export`.

This module exports the "申請總表" Excel report (single-department
xlsx + multi-department zip bundle). Two pure helpers + two MIME
constants are critical:

  - **XLSX_MEDIA_TYPE / ZIP_MEDIA_TYPE**: HTTP Content-Type strings.
    Wrong MIME → browser downloads with wrong extension/icon,
    Excel may refuse to open.

  - **_sanitise_filename_part(value)**: strips Windows-illegal
    characters from filename components. Department name → ZIP
    entry filename. A regression allowing `\\/:*?"<>|` would
    break ZIP creation on Windows extraction.

  - **_sort_key(a)**: sorts applications with renewal applications
    first, then by std_stdcode, with missing/blank student codes
    pushed to the END within each group. Renewal-first order
    matches the college ranking screen and roster list (issue #71).

13 cases.
"""

from types import SimpleNamespace

from app.api.v1.endpoints.college_review.application_summary_export import (
    XLSX_MEDIA_TYPE,
    ZIP_MEDIA_TYPE,
    _sanitise_filename_part,
    _sort_key,
)

# ─── MIME type constants ─────────────────────────────────────────────


def test_xlsx_media_type_is_openxml_spreadsheet():
    # Pin: the documented xlsx MIME. Browser uses this to decide
    # icon + extension on download.
    assert XLSX_MEDIA_TYPE == ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def test_zip_media_type_is_application_zip():
    # Pin: standard application/zip. Pin so a refactor to
    # "application/x-zip-compressed" doesn't silently break
    # browser-side download handling on some platforms.
    assert ZIP_MEDIA_TYPE == "application/zip"


# ─── _sanitise_filename_part ─────────────────────────────────────────


def test_sanitise_strips_backslash():
    assert _sanitise_filename_part(r"foo\bar") == "foo_bar"


def test_sanitise_strips_forward_slash():
    assert _sanitise_filename_part("foo/bar") == "foo_bar"


def test_sanitise_strips_all_windows_illegal_chars():
    # Pin: all 9 documented unsafe chars (\/:*?"<>|) replaced
    # with _. Critical — even ONE unsafe char in a ZIP entry
    # name breaks Windows extraction.
    assert _sanitise_filename_part(r'a\b/c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_sanitise_preserves_safe_characters():
    # Pin: alphanumerics, CJK, spaces, dashes pass through.
    assert _sanitise_filename_part("人社院 - 2025") == "人社院 - 2025"


def test_sanitise_strips_trailing_whitespace():
    # Pin: .strip() applied at end. Common bug source — trailing
    # spaces in ZIP entry names confuse extractors.
    assert _sanitise_filename_part("  hello  ") == "hello"


def test_sanitise_empty_string_returns_untitled():
    # Pin: empty input → "untitled" fallback. Pin so a refactor
    # returning empty string doesn't produce a ZIP entry with
    # empty name (which most tools reject).
    assert _sanitise_filename_part("") == "untitled"


def test_sanitise_whitespace_only_returns_untitled():
    # Pin: whitespace-only input → "untitled" after .strip() →
    # empty → fallback. Defensive against department names that
    # are accidentally just spaces.
    assert _sanitise_filename_part("   ") == "untitled"


# ─── _sort_key ──────────────────────────────────────────────────────


def _app(std_stdcode, app_id, is_renewal=False):
    """Build a duck-typed Application stand-in."""
    return SimpleNamespace(
        student_data={"std_stdcode": std_stdcode} if std_stdcode is not None else None,
        id=app_id,
        is_renewal=is_renewal,
    )


def test_sort_apps_with_codes_come_before_blank():
    # Pin: real student codes sort FIRST, blanks LAST. Admins
    # read the report top-down — real students should appear
    # before anomalies.
    apps = [
        _app("", 1),  # blank
        _app("310460031", 2),  # real
        _app(None, 3),  # missing student_data
    ]
    sorted_apps = sorted(apps, key=_sort_key)
    # Real code (id=2) first; blank (id=1) and None (id=3) after
    assert sorted_apps[0].id == 2


def test_sort_apps_blank_codes_sort_by_id_as_tiebreaker():
    # Pin: among apps with blank codes, id is the tiebreaker
    # (so the report is at least deterministic). Pin so a
    # refactor dropping the third tuple element doesn't make
    # the bottom of the report nondeterministic.
    apps = [_app("", 5), _app("", 2), _app("", 8)]
    sorted_apps = sorted(apps, key=_sort_key)
    ids = [a.id for a in sorted_apps]
    assert ids == [2, 5, 8]


def test_sort_apps_real_codes_sort_alphabetically():
    # Pin: real student codes sort by code string (alphabetical).
    apps = [_app("310460031", 1), _app("310460010", 2), _app("310460099", 3)]
    sorted_apps = sorted(apps, key=_sort_key)
    codes = [a.student_data["std_stdcode"] for a in sorted_apps]
    assert codes == ["310460010", "310460031", "310460099"]


def test_sort_handles_none_student_data_as_blank():
    # Pin: app.student_data=None → blank code → sorts LAST with
    # other blanks. Pin the (a.student_data or {}).get pattern
    # so a refactor that crashes on None doesn't break sorting
    # when the SIS API returned no data.
    apps = [_app(None, 1), _app("real", 2)]
    sorted_apps = sorted(apps, key=_sort_key)
    assert sorted_apps[0].id == 2
    assert sorted_apps[1].id == 1


def test_sort_renewal_apps_come_before_new_apps():
    # Pin: renewal applications (is_renewal=True) sort FIRST,
    # regardless of student code. Required by issue #71 — the
    # 申請總表 Excel must match the college ranking screen order
    # where renewal applications appear above new applications.
    apps = [
        _app("310460001", 1, is_renewal=False),  # new app, real code
        _app("310460002", 2, is_renewal=True),  # renewal, real code
        _app("", 3, is_renewal=False),  # new app, blank code
    ]
    sorted_apps = sorted(apps, key=_sort_key)
    # Renewal (id=2) must come first
    assert sorted_apps[0].id == 2
    # New apps follow, real code before blank
    assert sorted_apps[1].id == 1
    assert sorted_apps[2].id == 3
