"""Shared file-format constants for admin-managed reference documents."""

# Document formats accepted for admin-managed reference material
# (footer 相關連結 uploads): PDF, Microsoft Office, and OpenDocument (ODF).
# Mirrors the set used by 申請文件範例檔 / 補充參考文件 in system_settings.py.
REFERENCE_DOC_EXTENSIONS = [".pdf", ".doc", ".docx", ".odt", ".ods", ".odp"]


def extension_for_filename(filename: str) -> str:
    """Return the matching allowed extension for ``filename``, or "" if none."""
    lowered = (filename or "").lower()
    for ext in REFERENCE_DOC_EXTENSIONS:
        if lowered.endswith(ext):
            return ext
    return ""
