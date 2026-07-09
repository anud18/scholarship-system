"""Renewal-import service: parse a renewal-candidates sheet, keep the
renewal-passed rows, and create approved renewal applications for 造冊."""

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.models.application import Application, ApplicationStatus
from app.models.application_sequence import ApplicationSequence
from app.models.batch_import import BatchImport
from app.models.enums import BatchImportStatus, ReviewStage, Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.schemas.renewal_import import RenewalDataRow
from app.services.batch_import_service import _normalize_identifier, _normalize_optional
from app.services.student_service import StudentService

logger = logging.getLogger(__name__)

# 獎學金類別 label -> configuration sub-type code. Extend as new labels appear.
RENEWAL_SUB_TYPE_LABELS = {"國科會": "nstc", "教育部": "moe_1w", "教育部配合款2萬": "moe_2w"}
APPLIED_YES = "是"
PASS_MARK = "通過"


class RenewalImportService:
    def __init__(self, db: AsyncSession, student_service: Optional[StudentService] = None):
        self.db = db
        self.student_service = student_service or StudentService()

    async def parse_renewal_excel(
        self, file_content: bytes, scholarship_type_id: int, academic_year: int, semester: Optional[str]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return (parsed_rows, skipped_rows, errors). Only rows with
        學生是否申請續領=是 AND 續領審核結果=通過 land in parsed_rows."""
        errors: List[Dict[str, Any]] = []
        parsed: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        try:
            df = pd.read_excel(io.BytesIO(file_content))
        except Exception:
            try:
                df = pd.read_csv(io.BytesIO(file_content))
            except Exception as e:
                errors.append(
                    {
                        "row_number": 0,
                        "student_id": None,
                        "field": "file",
                        "error_type": "parse_error",
                        "message": f"無法解析檔案: {str(e)}",
                    }
                )
                return [], [], errors

        scholarship = await self.db.get(ScholarshipType, scholarship_type_id)
        if not scholarship:
            errors.append(
                {
                    "row_number": 0,
                    "student_id": None,
                    "field": "scholarship_type",
                    "error_type": "not_found",
                    "message": f"獎學金類型 ID {scholarship_type_id} 不存在",
                }
            )
            return [], [], errors

        real_sub_types = {st.lower() for st in (scholarship.sub_type_list or []) if st}
        df_columns = set(df.columns)
        required = ["學號", "學生姓名", "獎學金類別", "學生是否申請續領", "續領審核結果"]
        missing = [c for c in required if c not in df_columns]
        if missing:
            errors.append(
                {
                    "row_number": 0,
                    "student_id": None,
                    "field": "columns",
                    "error_type": "missing_columns",
                    "message": f"缺少必要欄位: {', '.join(missing)}",
                }
            )
            return [], [], errors

        seen: set = set()
        for idx, row in df.iterrows():
            row_number = idx + 2
            student_id = _normalize_identifier(row.get("學號", ""))
            if not student_id:
                continue

            applied = _normalize_identifier(row.get("學生是否申請續領", ""))
            result = _normalize_identifier(row.get("續領審核結果", ""))
            base = {
                "row_number": row_number,
                "student_id": student_id,
                "student_name": _normalize_identifier(row.get("學生姓名", "")),
                "applied_for_renewal": applied,
                "review_result": result,
            }

            # Filter: only 是 + 通過 rows are imported.
            if applied != APPLIED_YES or result != PASS_MARK:
                base["skip_reason"] = f"未通過 (申請續領={applied or '空'}, 審核結果={result or '空'})"
                skipped.append(base)
                continue

            if student_id in seen:
                errors.append(
                    {
                        "row_number": row_number,
                        "student_id": student_id,
                        "field": "student_id",
                        "error_type": "duplicate_in_file",
                        "message": f"學號 {student_id} 在檔案中重複",
                    }
                )
                continue
            seen.add(student_id)

            label = _normalize_identifier(row.get("獎學金類別", ""))
            sub_type = RENEWAL_SUB_TYPE_LABELS.get(label, label.lower())
            if sub_type not in real_sub_types:
                errors.append(
                    {
                        "row_number": row_number,
                        "student_id": student_id,
                        "field": "獎學金類別",
                        "error_type": "invalid_sub_type",
                        "message": f"獎學金類別「{label}」無法對應到有效子類型（{'、'.join(sorted(real_sub_types))}）",
                    }
                )
                continue

            data_row = {
                "student_id": student_id,
                "student_name": base["student_name"],
                "sub_type": sub_type,
                "postal_account": _normalize_optional(row.get("郵局帳號")),
                "advisor_nycu_id": _normalize_optional(row.get("指導教授本校人事編號")),
                "advisor_name": _normalize_optional(row.get("指導教授姓名")),
            }
            try:
                normalized = RenewalDataRow(**data_row).model_dump()
                normalized["row_number"] = row_number
                parsed.append(normalized)
            except Exception as e:  # noqa: BLE001 - surface row validation errors
                errors.append(
                    {
                        "row_number": row_number,
                        "student_id": student_id,
                        "field": "row_data",
                        "error_type": "validation_error",
                        "message": f"資料驗證失敗: {str(e)}",
                    }
                )

        return parsed, skipped, errors
