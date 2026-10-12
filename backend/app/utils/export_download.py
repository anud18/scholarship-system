"""Shared HTTP-download helpers for binary file exports.

Every export endpoint returns a ``StreamingResponse`` with an RFC 5987
``Content-Disposition`` (filenames are CJK, so plain ``filename=`` breaks) and
an explicit ``Content-Length``. These constants and the filename scrubber were
originally private to ``college_review/application_summary_export``; they moved
here when the manual-distribution 分發名單 export — a different endpoint
package — needed them too.
"""

import re
from urllib.parse import quote

from fastapi.responses import StreamingResponse

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ZIP_MEDIA_TYPE = "application/zip"

# Characters not allowed in cross-platform filenames
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|]')


def sanitise_filename_part(value: str) -> str:
    """Make one filename component safe on Windows/macOS/Linux.

    Replaces the illegal characters with ``_`` and trims surrounding
    whitespace; an empty (or whitespace-only) result becomes ``untitled`` so a
    download never gets a nameless component.
    """
    return _UNSAFE_FILENAME_RE.sub("_", value).strip() or "untitled"


def xlsx_attachment_response(payload: bytes, filename: str) -> StreamingResponse:
    """Stream an in-memory .xlsx as an RFC 5987 attachment with Content-Length."""
    return StreamingResponse(
        iter([payload]),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
            "Content-Length": str(len(payload)),
        },
    )
