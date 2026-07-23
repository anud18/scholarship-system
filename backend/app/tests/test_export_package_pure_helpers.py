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
- FILE_TYPE_LABELS: zh-TW labels for the known fixed file types
- DEGREE_LABELS: zh-TW labels for degrees 1/2/3
- _is_dynamic_document_type / _unique_zip_path: merged-PDF selector
  and duplicate-entry defense

Skips _build_table / _generate_summary_pdf because they depend
on reportlab Paragraph + CJK font registration that runs at
class instantiation (not a pure-helper test).
"""

import pytest

from app.services.export_package_service import (
    _sanitize_filename,
    _label_for_file_type,
    _is_dynamic_document_type,
    _unique_zip_path,
    _fetch_and_write,
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
    """Pin: FILE_TYPE_LABELS — zh-TW labels for the fixed file types.
    Used by the export PDF and ZIP folder naming, AND as the negative
    membership test for the dynamic-documents merge selector."""

    def test_all_11_known_file_types_present(self):
        # Pin: exactly 11 file types. bank_account_proof is the
        # value actually stored on the cloned passbook
        # ApplicationFile (application_service.py:2118); id_card and
        # bank_book are minted by batch_import's doc_type_map. Every
        # fixed type MUST be listed here or it is misclassified as an
        # admin-configured dynamic document and swept into the merged
        # 動態文件合併.pdf.
        expected_keys = {
            "transcript",
            "research_proposal",
            "recommendation_letter",
            "certificate",
            "insurance_record",
            "agreement",
            "bank_account_cover",
            "bank_account_proof",
            "id_card",
            "bank_book",
            "other",
        }
        assert set(FILE_TYPE_LABELS.keys()) == expected_keys

    def test_batch_import_types_are_fixed_not_dynamic(self):
        # Pin: batch_import mints these internal type strings
        # (batch_import.py doc_type_map); they carry sensitive PII and
        # must never join the reviewer-facing merged dynamic PDF.
        assert FILE_TYPE_LABELS["id_card"] == "身份證"
        assert FILE_TYPE_LABELS["bank_book"] == "存摺封面"
        assert _is_dynamic_document_type("id_card") is False
        assert _is_dynamic_document_type("bank_book") is False

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


class TestLabelForFileType:
    """Pin: ZIP filename labels. Fixed types map through
    FILE_TYPE_LABELS; admin-configured dynamic document types keep
    their configured name (the ApplicationFile file_type IS the
    configured document_name) so each configured document stays
    identifiable in the export."""

    def test_fixed_type_maps_to_zh_label(self):
        assert _label_for_file_type("transcript") == "成績單"

    def test_dynamic_custom_type_keeps_its_configured_name(self):
        # An admin-defined dynamic document (e.g. 語言檢定證明) is not in
        # FILE_TYPE_LABELS — the export must keep the configured name,
        # NOT collapse it into 其他文件.
        assert _label_for_file_type("語言檢定證明") == "語言檢定證明"

    def test_other_maps_to_generic_label(self):
        assert _label_for_file_type("other") == "其他文件"

    def test_empty_type_maps_to_generic_label(self):
        assert _label_for_file_type("") == "其他文件"


class TestIsDynamicDocumentType:
    """Pin: the merged-PDF selector. Only admin-configured dynamic documents
    (file_type IS the configured document_name) join the per-student
    動態文件合併.pdf; every fixed type and the 其他文件 bucket stay out."""

    @pytest.mark.parametrize("fixed_type", sorted(FILE_TYPE_LABELS.keys()))
    def test_every_fixed_type_is_not_dynamic(self, fixed_type):
        assert _is_dynamic_document_type(fixed_type) is False

    def test_configured_document_name_is_dynamic(self):
        assert _is_dynamic_document_type("語言檢定證明") is True

    def test_empty_and_none_are_not_dynamic(self):
        assert _is_dynamic_document_type("") is False
        assert _is_dynamic_document_type(None) is False


class TestUniqueZipPath:
    """Pin: duplicate-entry defense. zipfile writes duplicate names without
    error and most extractors keep only the last, silently shadowing a file
    (e.g. a dynamic document named 動態文件合併 vs the merged artifact)."""

    def _zf_with(self, names):
        import io
        import zipfile

        buf = io.BytesIO()
        zf = zipfile.ZipFile(buf, "w")
        for n in names:
            zf.writestr(n, b"x")
        return zf

    def test_free_path_returned_unchanged(self):
        zf = self._zf_with(["a/b.pdf"])
        assert _unique_zip_path(zf, "a/c.pdf") == "a/c.pdf"

    def test_collision_gets_counter_before_extension(self):
        zf = self._zf_with(["a/b.pdf"])
        assert _unique_zip_path(zf, "a/b.pdf") == "a/b_2.pdf"

    def test_counter_skips_taken_names(self):
        zf = self._zf_with(["a/b.pdf", "a/b_2.pdf"])
        assert _unique_zip_path(zf, "a/b.pdf") == "a/b_3.pdf"

    def test_extensionless_path_gets_plain_suffix(self):
        zf = self._zf_with(["a/readme"])
        assert _unique_zip_path(zf, "a/readme") == "a/readme_2"


class TestFetchAndWrite:
    """Pin: the shared MinIO fetch-and-write used by the app.files
    loop. On success the bytes land at zip_path; on any MinIO error
    a placeholder .txt lands at error_path instead (the ZIP build
    never aborts)."""

    def test_success_writes_bytes_and_releases_connection(self):
        import asyncio
        import io
        import zipfile
        from unittest.mock import MagicMock

        fake_response = MagicMock()
        fake_response.read.return_value = b"PDF-BYTES"
        minio = MagicMock()
        minio.get_file_stream.return_value = fake_response

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            returned = asyncio.run(
                _fetch_and_write(
                    zf,
                    minio,
                    object_name="application-documents/12_x.pdf",
                    zip_path="dept/stu/stu_申請文件.pdf",
                    error_path="dept/stu/_錯誤_找不到檔案_申請文件.txt",
                    error_label="申請文件.pdf",
                )
            )

        # Pin: success returns the fetched bytes (reused for the merged
        # dynamic-documents PDF without a second MinIO round-trip).
        assert returned == b"PDF-BYTES"
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            assert zf.read("dept/stu/stu_申請文件.pdf") == b"PDF-BYTES"
            assert "dept/stu/_錯誤_找不到檔案_申請文件.txt" not in zf.namelist()
        fake_response.close.assert_called_once()
        fake_response.release_conn.assert_called_once()

    def test_failure_writes_error_placeholder(self):
        import asyncio
        import io
        import zipfile
        from unittest.mock import MagicMock

        minio = MagicMock()
        minio.get_file_stream.side_effect = Exception("object missing")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            returned = asyncio.run(
                _fetch_and_write(
                    zf,
                    minio,
                    object_name="application-documents/12_x.pdf",
                    zip_path="dept/stu/stu_申請文件.pdf",
                    error_path="dept/stu/_錯誤_找不到檔案_申請文件.txt",
                    error_label="申請文件.pdf",
                )
            )

        # Pin: failure returns None (caller renders a download-failure
        # placeholder page in the merged PDF instead of file bytes).
        assert returned is None
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "dept/stu/stu_申請文件.pdf" not in names
            assert "dept/stu/_錯誤_找不到檔案_申請文件.txt" in names
            content = zf.read("dept/stu/_錯誤_找不到檔案_申請文件.txt").decode("utf-8")
            assert "object missing" in content
            assert "申請文件.pdf" in content
