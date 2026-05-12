"""
Application Summary (申請總表) Excel Export Endpoints

Two endpoints, both under /api/v1/college-review/applications/:
- GET /department-summary-export       → single department .xlsx
- GET /department-summary-export-bulk  → multi-department .zip

Reuses CollegeRankingExportService with ExportRow.rank_position=None so the
學院初審會議之學院排序 column renders empty cells.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from typing import Optional
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import require_college
from app.db.deps import get_db
from app.models.application import Application
from app.models.scholarship import ScholarshipType
from app.models.student import Department
from app.models.user import User, UserRole
from app.services.college_ranking_export_service import (
    CollegeRankingExportService,
    ExportRow,
)

from ._helpers import load_export_aux_data, normalize_semester_value

logger = logging.getLogger(__name__)

router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ZIP_MEDIA_TYPE = "application/zip"

# Characters not allowed in cross-platform filenames
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|]')


def _sanitise_filename_part(value: str) -> str:
    return _UNSAFE_FILENAME_RE.sub("_", value).strip() or "untitled"
