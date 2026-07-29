"""Shared file-format constants for admin-managed reference documents."""

# Document formats accepted for admin-managed reference material
# (footer 相關連結 uploads): PDF, Microsoft Office, and OpenDocument (ODF).
# Mirrors the set used by 申請文件範例檔 / 補充參考文件 in system_settings.py.
REFERENCE_DOC_EXTENSIONS = [".pdf", ".doc", ".docx", ".odt", ".ods", ".odp"]

# Server-side MIME type per allowed extension. The multipart Content-Type a
# client declares is attacker-controlled and MUST NOT be persisted or echoed
# back: a file named .pdf but declared text/html would be served inline from
# our own origin. Always derive the type from the validated extension instead.
_CONTENT_TYPE_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
}


def extension_for_filename(filename: str) -> str:
    """Return the matching allowed extension for ``filename``, or "" if none."""
    lowered = (filename or "").lower()
    for ext in REFERENCE_DOC_EXTENSIONS:
        if lowered.endswith(ext):
            return ext
    return ""


def content_type_for_extension(ext: str) -> str:
    """Trusted Content-Type for an already-validated extension.

    Falls back to application/octet-stream, which browsers download rather
    than render, so an unrecognised extension can never become a live
    same-origin document.
    """
    return _CONTENT_TYPE_BY_EXTENSION.get((ext or "").lower(), "application/octet-stream")
