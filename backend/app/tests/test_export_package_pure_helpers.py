"""
Tests for `backend/app/services/export_package_service.py` —
module-level pure helpers + constants.

Module had ZERO test references. SECURITY-CRITICAL filename
sanitization (ZIP path traversal vector) + zh-TW label
constants that drive admin export filenames and PDF rendering.

Wave 6a143 pins the pure helpers without invoking the reportlab
font registration / MinIO / DB paths:
- _sanitize_filename: 9 invalid-char sanitization + SECURITY
  path-traversal prevention
- FILE_TYPE_LABELS: zh-TW labels for the 8 known file types
- DEGREE_LABELS: zh-TW labels for degrees 1/2/3

Skips _build_table / _generate_summary_pdf because they depend
on reportlab Paragraph + CJK font registration that runs at
class instantiation (not a pure-helper test).
"""

import pytest

from app.services.export_package_service import (
    _sanitize_filename,
    _ext_for_application_document,
    FILE_TYPE_LABELS,
    DEGREE_LABELS,
)


class TestSanitizeFilename:
    """Pin SECURITY: filename sanitization prevents ZIP-path-
    traversal attacks. Drift would let malicious admin-uploaded
    or SIS-API-supplied filenames escape the ZIP root."""

    @pytest.mark.parametrize(
        "invalid_char",
        ["/", "\\", ":", "*", "?", '"', "<", ">", "|"],
    )
    def test_invalid_char_replaced_with_underscore(self, invalid_char):
        # Pin: all 9 illegal characters per Windows + POSIX ZIP
        # spec are replaced with underscore. Pin so refactor
        # doesn't drop any one (any single drop enables traversal
        # on the omitted character's platform).
        result = _sanitize_filename(f"file{invalid_char}name")
        assert invalid_char not in result
        assert "_" in result

    def test_strips_leading_and_trailing_whitespace(self):
        # Pin: .strip() applied after substitution. Pin so refactor
        # doesn't accidentally lose whitespace-stripping which
        # would let "   admin.pdf" sort differently from
        # "admin.pdf" in the ZIP listing.
        result = _sanitize_filename("  test.pdf  ")
        assert result == "test.pdf"

    def test_cjk_chars_preserved(self):
        # Pin: zh-TW Chinese characters are preserved (NOT
        # transliterated or stripped). Pin so admin-uploaded
        # 學生姓名 keeps the Chinese name in the ZIP.
        result = _sanitize_filename("王小明.pdf")
        assert result == "王小明.pdf"

    def test_path_traversal_via_slashes_blocked(self):
        # Pin SECURITY: "../../../etc/passwd" style traversal
        # via / replaced. After sanitization, the path becomes
        # "..______etc_passwd" — no separator survives.
        result = _sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert "\\" not in result
        # ".." remains as plain chars (NOT a separator) — that's
        # fine because the ZIP libs treat it literally without "/"
        assert ".." in result

    def test_windows_path_traversal_blocked(self):
        # Pin SECURITY: Windows-style backslash separators blocked.
        result = _sanitize_filename("..\\..\\Windows\\System32\\config")
        assert "\\" not in result

    def test_pipe_redirection_blocked(self):
        # Pin SECURITY: shell-redirection chars stripped. Pin
        # because some downstream tooling (e.g. unzip into a
        # filesystem with `find -exec`) would interpret these.
        result = _sanitize_filename("normal|piped")
        assert "|" not in result

    def test_empty_string_returns_empty(self):
        # Pin: empty input → empty output (NOT raise). Caller
        # responsible for handling empty filenames.
        assert _sanitize_filename("") == ""

    def test_only_invalid_chars_collapses_to_underscores(self):
        # Pin: all-invalid input → all underscores (no exception).
        result = _sanitize_filename("///\\\\:::")
        assert all(c == "_" for c in result)


class TestFileTypeLabels:
    """Pin: FILE_TYPE_LABELS — zh-TW labels for 8 file types.
    Used by the export PDF and ZIP folder naming."""

    def test_all_9_known_file_types_present(self):
        # Pin: exactly 9 file types. bank_account_proof is the
        # value actually stored on the cloned passbook
        # ApplicationFile (application_service.py:2118); it must
        # have a label or it falls through to the 其他文件 default.
        expected_keys = {
            "transcript",
            "research_proposal",
            "recommendation_letter",
            "certificate",
            "insurance_record",
            "agreement",
            "bank_account_cover",
            "bank_account_proof",
            "other",
        }
        assert set(FILE_TYPE_LABELS.keys()) == expected_keys

    def test_transcript_label_is_zh_tw(self):
        # Pin: zh-TW is the system default per CLAUDE.md.
        assert FILE_TYPE_LABELS["transcript"] == "成績單"

    def test_bank_account_cover_label(self):
        # Pin: 存摺封面 is the canonical zh-TW label. Pin so refactor
        # doesn't change to 銀行帳戶 which would mismatch the
        # admin UI's existing strings.
        assert FILE_TYPE_LABELS["bank_account_cover"] == "存摺封面"

    def test_bank_account_proof_label(self):
        # Pin: the cloned passbook's real file_type
        # (bank_account_proof) maps to 存摺封面 so it stops landing
        # under 其他文件 in the export ZIP.
        assert FILE_TYPE_LABELS["bank_account_proof"] == "存摺封面"

    def test_all_labels_are_non_empty_chinese(self):
        # Pin: every label is non-empty and contains CJK chars.
        for key, label in FILE_TYPE_LABELS.items():
            assert label, f"FILE_TYPE_LABELS[{key!r}] is empty"
            # Quick CJK check — at least one char in the CJK range
            assert any("一" <= c <= "鿿" for c in label), f"FILE_TYPE_LABELS[{key!r}] = {label!r} has no CJK character"


class TestDegreeLabels:
    """Pin: DEGREE_LABELS — zh-TW labels for the 3 NYCU degree
    codes used by the SIS API."""

    def test_three_degree_codes(self):
        # Pin: exactly 3 degree levels keyed by STRING numbers
        # (NOT integer — SIS API returns int but the lookup keys
        # are strings). Pin so refactor doesn't change key type
        # and break the lookup silently (returning "Unknown").
        assert set(DEGREE_LABELS.keys()) == {"1", "2", "3"}

    def test_degree_labels_are_zh_tw(self):
        # Pin: zh-TW canonical names — 學士/碩士/博士.
        assert DEGREE_LABELS["1"] == "學士"
        assert DEGREE_LABELS["2"] == "碩士"
        assert DEGREE_LABELS["3"] == "博士"

    def test_keys_are_strings_not_ints(self):
        # Pin: SIS API returns std_degree as INT but the labels
        # dict keys are STRINGS. Callers must coerce via str().
        # Pin so refactor unifying to int keys (or vice versa)
        # is explicit.
        for key in DEGREE_LABELS:
            assert isinstance(key, str), f"DEGREE_LABELS key {key!r} is not str"


class TestExtForApplicationDocument:
    """Pin: extension derivation for the student-uploaded 申請文件.
    Prefers the original filename's extension, falls back to the
    stored MinIO object name's suffix."""

    def test_uses_original_filename_extension(self):
        assert _ext_for_application_document("申請文件.pdf", "application-documents/12_x.pdf") == ".pdf"

    def test_original_filename_extension_wins_over_object_name(self):
        assert _ext_for_application_document("draft.docx", "application-documents/12_x.pdf") == ".docx"

    def test_falls_back_to_object_name_when_no_original(self):
        assert _ext_for_application_document(None, "application-documents/12_x.pdf") == ".pdf"

    def test_empty_original_falls_back_to_object_name(self):
        assert _ext_for_application_document("", "application-documents/12_x.pdf") == ".pdf"

    def test_returns_empty_when_no_extension_anywhere(self):
        assert _ext_for_application_document("noext", "application-documents/12_x") == ""

    def test_directory_dot_not_mistaken_for_extension(self):
        # A dot in a directory segment must not be treated as the
        # file extension — only the last path segment counts.
        assert _ext_for_application_document(None, "v1.2/objectname") == ""
