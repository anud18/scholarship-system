"""
SECURITY-CRITICAL tests for `app.core.path_security`.

CLAUDE.md mandates a triple-validation pattern for every file-handling
endpoint:
  1. Check for `..`, `/`, `\\` (path traversal)
  2. Regex allowlist for filename characters
  3. Resolve to absolute path and verify it's within expected directory

These helpers implement that pattern. They are the single point of
truth for filename safety across MinIO uploads, bank-document storage,
and college-export downloads. A regression here would expose:
- Path traversal: filename `../../../etc/passwd` reading outside the
  bucket / upload directory
- Null-byte injection: `safe.pdf\0.exe` masquerading as PDF
- Length-based DoS: 100KB filenames consuming memory in path operations
- Extension allowlist bypass: `.pdf.exe` slipping past extension check

5 functions covered (26 cases). No network, no DB.
"""

import pytest
from fastapi import HTTPException

from app.core.path_security import (
    secure_filename,
    validate_filename_strict,
    validate_object_name_minio,
    validate_path_in_directory,
    validate_upload_file,
)

# ─── validate_filename_strict — ASCII mode ───────────────────────────


def test_filename_strict_empty_rejected():
    """Pin: empty string raises 400. Otherwise a missing filename slips
    into MinIO with key='' → silent overwrite of bucket root."""
    with pytest.raises(HTTPException) as exc:
        validate_filename_strict("")
    assert exc.value.status_code == 400


def test_filename_strict_path_traversal_rejected():
    """SECURITY-CRITICAL: '..' / '/' / '\\\\' patterns rejected. Pin
    all three — different OS path conventions."""
    for malicious in ["../etc/passwd", "..\\windows\\system32", "subdir/file.pdf", "subdir\\file.pdf", "good..bad"]:
        with pytest.raises(HTTPException) as exc:
            validate_filename_strict(malicious)
        assert exc.value.status_code == 400, f"failed to reject: {malicious}"


def test_filename_strict_ascii_allowlist():
    """Pin: only [a-zA-Z0-9_-.] allowed in default mode."""
    for good in ["file.pdf", "report_2024.xlsx", "report-final.docx", "ABC123.txt"]:
        validate_filename_strict(good)  # should not raise


def test_filename_strict_unicode_rejected_in_ascii_mode():
    """Pin: default ASCII mode rejects Chinese characters."""
    with pytest.raises(HTTPException):
        validate_filename_strict("成績單.pdf")


def test_filename_strict_special_chars_rejected_ascii():
    """Pin: spaces, $, !, @, etc. all rejected in ASCII mode."""
    for bad in ["my file.pdf", "report$.pdf", "test!.pdf", "name@home.pdf"]:
        with pytest.raises(HTTPException):
            validate_filename_strict(bad)


def test_filename_strict_length_cap():
    """Pin: 255-char max. Defends against pathological-length filenames
    that could DoS path-construction code paths."""
    with pytest.raises(HTTPException) as exc:
        validate_filename_strict("x" * 256 + ".pdf")  # 260 chars
    assert exc.value.status_code == 400


def test_filename_strict_at_max_length_accepted():
    """Pin: exactly 255 chars is OK (the cap is inclusive)."""
    name = "x" * 251 + ".pdf"  # 255 chars total
    validate_filename_strict(name)  # should not raise


# ─── validate_filename_strict — Unicode mode ─────────────────────────


def test_filename_unicode_mode_chinese_accepted():
    """Pin: allow_unicode=True permits CJK characters in filenames."""
    validate_filename_strict("成績單.pdf", allow_unicode=True)
    validate_filename_strict("申請書_王小明.docx", allow_unicode=True)


def test_filename_unicode_mode_dangerous_chars_still_rejected():
    """Pin: even in Unicode mode, `|<>:"?*` are blocked. These are
    Windows reserved characters AND common shell-injection vectors."""
    for bad in ["pipe|.pdf", "lt<.pdf", "gt>.pdf", "colon:.pdf", 'quote".pdf', "question?.pdf", "star*.pdf"]:
        with pytest.raises(HTTPException):
            validate_filename_strict(bad, allow_unicode=True)


def test_filename_unicode_mode_path_traversal_still_rejected():
    """Pin: ../, /, \\\\ still rejected in Unicode mode. Defensive — the
    Unicode-mode relaxation only loosens the *character allowlist*, not
    the path traversal guard."""
    with pytest.raises(HTTPException):
        validate_filename_strict("../成績單.pdf", allow_unicode=True)


# ─── validate_path_in_directory ──────────────────────────────────────


def test_path_within_directory_accepted():
    validate_path_in_directory("/var/uploads/bank_docs/file.pdf", "/var/uploads/bank_docs")
    validate_path_in_directory("/var/uploads/bank_docs/subdir/file.pdf", "/var/uploads")


def test_path_outside_directory_rejected():
    """SECURITY-CRITICAL: pin so a relative path that resolves outside
    the expected directory is rejected. This is the third layer of
    defense (after filename validation)."""
    with pytest.raises(HTTPException) as exc:
        validate_path_in_directory("/etc/passwd", "/var/uploads/bank_docs")
    assert exc.value.status_code == 403


def test_path_with_relative_traversal_rejected():
    """Pin: os.path.abspath resolves '..' segments → catches the
    classic '/expected/dir/../../etc/passwd' attack."""
    with pytest.raises(HTTPException):
        validate_path_in_directory("/var/uploads/bank_docs/../../etc/passwd", "/var/uploads/bank_docs")


# ─── validate_object_name_minio ──────────────────────────────────────


def test_minio_object_name_valid_accepted():
    validate_object_name_minio("scholarship-system/applications/123/bank_doc.pdf")


def test_minio_object_name_empty_rejected():
    with pytest.raises(HTTPException):
        validate_object_name_minio("")


def test_minio_object_name_absolute_path_rejected():
    """Pin: absolute paths rejected. MinIO objects must be relative."""
    with pytest.raises(HTTPException) as exc:
        validate_object_name_minio("/etc/passwd")
    assert exc.value.status_code == 400


def test_minio_object_name_traversal_segment_rejected():
    """Pin: any '..' segment in the path rejected. Defends against
    `subdir/../../escape` patterns."""
    for malicious in ["subdir/../escape.pdf", "../escape.pdf", "subdir/./file.pdf"]:
        with pytest.raises(HTTPException) as exc:
            validate_object_name_minio(malicious)
        assert exc.value.status_code == 400


def test_minio_object_name_double_slash_rejected():
    """Pin: double slashes (empty path segment) rejected. Defends
    against `subdir//file.pdf` which some path libraries handle
    inconsistently."""
    with pytest.raises(HTTPException):
        validate_object_name_minio("subdir//file.pdf")


# ─── secure_filename (sanitize-not-reject) ───────────────────────────


def test_secure_filename_replaces_special_chars():
    """Pin: in ASCII mode, non-allowlist chars → underscore."""
    assert secure_filename("my file!.pdf") == "my_file_.pdf"


def test_secure_filename_collapses_underscores():
    """Pin: consecutive underscores collapse to one. Defensive against
    `my___file___.pdf` → `my_file_.pdf` → `my_file_.pdf` (single _ between
    name and ext)."""
    assert secure_filename("my___file.pdf") == "my_file.pdf"


def test_secure_filename_strips_path_components():
    """SECURITY-CRITICAL: os.path.basename() removes leading directories.
    `../../../etc/passwd` → `passwd`."""
    assert secure_filename("../../../etc/passwd") == "passwd"
    assert secure_filename("/var/log/something.log") == "something.log"


def test_secure_filename_empty_after_sanitize_gets_default():
    """Pin: if sanitization strips everything → 'unnamed_file'. Defensive
    against filenames like '..' or '/' that have no safe characters."""
    assert secure_filename("___") == "unnamed_file"
    assert secure_filename("") == "unnamed_file"


def test_secure_filename_truncates_long_names_preserving_extension():
    """Pin: 255-char cap preserves the extension. Otherwise a long PDF
    name becomes a long text file silently."""
    long_name = "x" * 300 + ".pdf"
    result = secure_filename(long_name)
    assert len(result) <= 255
    assert result.endswith(".pdf")


def test_secure_filename_unicode_mode_keeps_chinese():
    """Pin: allow_unicode=True keeps CJK chars but still strips dangerous chars."""
    assert secure_filename("成績單.pdf", allow_unicode=True) == "成績單.pdf"
    # Dangerous chars in unicode mode → underscore
    assert secure_filename("成|績單.pdf", allow_unicode=True) == "成_績單.pdf"


# ─── validate_upload_file (composite gate) ───────────────────────────


def test_upload_file_valid_payload():
    """Standard PDF upload — all gates pass."""
    result = validate_upload_file(
        filename="report.pdf",
        allowed_extensions=[".pdf"],
        max_size_mb=5,
        file_size=1024 * 100,  # 100 KB
    )
    assert result == "report.pdf"


def test_upload_file_extension_allowlist_enforced():
    """Pin: extension not in allowlist → 415."""
    with pytest.raises(HTTPException) as exc:
        validate_upload_file(filename="virus.exe", allowed_extensions=[".pdf", ".jpg"])
    assert exc.value.status_code == 415


def test_upload_file_double_extension_attack():
    """Pin: filename like `report.pdf.exe` is rejected — endswith
    check looks at the FINAL extension. Defensive against admins
    typo-uploading masqueraded files."""
    with pytest.raises(HTTPException):
        validate_upload_file(filename="report.pdf.exe", allowed_extensions=[".pdf"])


def test_upload_file_size_cap_enforced():
    """Pin: file_size > max_size_mb → 413."""
    with pytest.raises(HTTPException) as exc:
        validate_upload_file(
            filename="big.pdf",
            allowed_extensions=[".pdf"],
            max_size_mb=1,
            file_size=2 * 1024 * 1024,  # 2 MB
        )
    assert exc.value.status_code == 413


def test_upload_file_size_check_skipped_when_size_unknown():
    """Pin: file_size=None means 'size unknown, skip check'. Otherwise
    streaming uploads where size isn't pre-known would be rejected."""
    result = validate_upload_file(
        filename="report.pdf",
        allowed_extensions=[".pdf"],
        max_size_mb=1,
        file_size=None,
    )
    assert result == "report.pdf"
