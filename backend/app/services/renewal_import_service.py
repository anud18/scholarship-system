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


def _to_semester_enum(semester: Optional[str]) -> Optional[Semester]:
    """Map a raw semester string to the enum; yearly/annual/None -> None."""
    if semester in (None, "", "yearly", "annual"):
        return None
    try:
        return Semester(semester)
    except ValueError:
        return None


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

    async def validate_and_preview(
        self,
        parsed_rows: List[Dict[str, Any]],
        college_code: str,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Per-row SIS existence + duplicate-renewal errors, and postal/quota warnings."""
        errors: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        if not parsed_rows:
            return errors, warnings

        student_ids = [r["student_id"] for r in parsed_rows]

        # SIS existence check (real recipients must resolve to a snapshot at 造冊 time).
        if getattr(self.student_service, "api_enabled", False):
            for r in parsed_rows:
                sid = r["student_id"]
                try:
                    info = await self.student_service.get_student_basic_info(sid)
                except ServiceUnavailableError:
                    warnings.append(
                        {
                            "row_number": r["row_number"],
                            "student_id": sid,
                            "field": "學號",
                            "warning_type": "student_api_unavailable",
                            "message": "學籍系統暫時不可用，請稍後重試。",
                        }
                    )
                    break
                except Exception:  # noqa: BLE001 - a single-row SIS error must not abort the whole preview
                    logger.warning("SIS error for %s", sid, exc_info=True)
                    continue
                if not info:
                    errors.append(
                        {
                            "row_number": r["row_number"],
                            "student_id": sid,
                            "field": "學號",
                            "error_type": "sis_not_found",
                            "message": f"學籍系統查無學號 {sid}，無法建立可造冊的續領。",
                        }
                    )

        # Missing postal account -> excluded from roster Excel (warn only).
        for r in parsed_rows:
            if not r.get("postal_account"):
                warnings.append(
                    {
                        "row_number": r["row_number"],
                        "student_id": r["student_id"],
                        "field": "郵局帳號",
                        "warning_type": "missing_postal_account",
                        "message": f"學號 {r['student_id']} 缺少郵局帳號，造冊時將被排除。",
                    }
                )

        # Duplicate approved/renewal check + over-quota warning.
        semester_enum = _to_semester_enum(semester)
        users_stmt = select(User).where(User.nycu_id.in_(student_ids))
        users = (await self.db.execute(users_stmt)).scalars().all()
        user_by_nycu = {u.nycu_id: u for u in users}
        if user_by_nycu:
            # deleted_at IS NULL mirrors the partial unique index uq_user_renewal_app
            # (is_renewal = true AND deleted_at IS NULL); a soft-deleted prior renewal
            # does not block a fresh insert, so it must not raise a false duplicate.
            dup_stmt = select(Application).where(
                Application.user_id.in_([u.id for u in users]),
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.is_renewal.is_(True),
                Application.deleted_at.is_(None),
            )
            dup_stmt = (
                dup_stmt.where(Application.semester.is_(None))
                if semester_enum is None
                else dup_stmt.where(Application.semester == semester_enum)
            )
            existing = {a.user_id for a in (await self.db.execute(dup_stmt)).scalars().all()}
            for r in parsed_rows:
                u = user_by_nycu.get(r["student_id"])
                if u and u.id in existing:
                    errors.append(
                        {
                            "row_number": r["row_number"],
                            "student_id": r["student_id"],
                            "field": "duplicate",
                            "error_type": "duplicate_renewal",
                            "message": f"學號 {r['student_id']} 已有此獎學金 {academic_year} 學年度的續領申請。",
                        }
                    )

        await self._append_quota_warnings(parsed_rows, scholarship_type_id, academic_year, semester_enum, warnings)
        return errors, warnings

    async def _append_quota_warnings(self, parsed_rows, scholarship_type_id, academic_year, semester_enum, warnings):
        from app.services.manual_distribution_service import ManualDistributionService

        config_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
            ScholarshipConfiguration.academic_year == academic_year,
        )
        config_stmt = (
            config_stmt.where(ScholarshipConfiguration.semester.is_(None))
            if semester_enum in (None, Semester.yearly)
            else config_stmt.where(ScholarshipConfiguration.semester == semester_enum)
        )
        config = (await self.db.execute(config_stmt)).scalar_one_or_none()
        if not config or not config.quotas:
            return
        md = ManualDistributionService(self.db)
        counts: Dict[str, int] = {}
        for r in parsed_rows:
            counts[r["sub_type"]] = counts.get(r["sub_type"], 0) + 1
        for sub_type, incoming in counts.items():
            quota_map = config.quotas.get(sub_type) or {}
            total_quota = (
                sum(int(v) for v in quota_map.values()) if isinstance(quota_map, dict) else int(quota_map or 0)
            )
            current = await md.consumers_count(config.id, sub_type)
            if total_quota and current + incoming > total_quota:
                warnings.append(
                    {
                        "row_number": None,
                        "student_id": None,
                        "field": sub_type,
                        "warning_type": "over_quota",
                        "message": f"子類型 {sub_type} 匯入後將達 {current + incoming} 人，超過配額 {total_quota} 人。",
                    }
                )

    async def _get_or_create_users_bulk(self, rows: List[Dict[str, Any]]) -> Dict[str, User]:
        """Delegate bulk user get/create to BatchImportService (shared logic)."""
        from app.services.batch_import_service import BatchImportService

        return await BatchImportService(self.db, self.student_service)._get_or_create_users_bulk(rows)

    async def create_renewal_import_record(
        self,
        importer_id: int,
        college_code: str,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        file_name: str,
        total_records: int,
    ) -> BatchImport:
        """Create the BatchImport record for a renewal import (import_type='renewal')."""
        batch_import = BatchImport(
            importer_id=importer_id,
            college_code=college_code,
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
            file_name=file_name,
            total_records=total_records,
            import_status=BatchImportStatus.pending.value,
            import_type="renewal",
            data_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        self.db.add(batch_import)
        await self.db.flush()
        return batch_import

    async def create_renewals_from_batch(
        self,
        batch_import: BatchImport,
        parsed_rows: List[Dict[str, Any]],
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
    ) -> Tuple[List[int], List[Dict[str, Any]]]:
        """Create approved renewal Applications (all-or-nothing) shaped so 造冊 includes them."""
        from app.core.exceptions import BatchImportError

        created_ids: List[int] = []
        errors: List[Dict[str, Any]] = []

        scholarship = await self.db.get(ScholarshipType, scholarship_type_id)
        if not scholarship:
            raise BatchImportError(message=f"獎學金類型 ID {scholarship_type_id} 不存在", batch_id=batch_import.id)

        semester_enum = _to_semester_enum(semester)
        config_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
            ScholarshipConfiguration.academic_year == academic_year,
        )
        config_stmt = (
            config_stmt.where(ScholarshipConfiguration.semester.is_(None))
            if semester_enum in (None, Semester.yearly)
            else config_stmt.where(ScholarshipConfiguration.semester == semester_enum)
        )
        config = (await self.db.execute(config_stmt)).scalar_one_or_none()
        if not config:
            raise BatchImportError(
                message=f"找不到 {academic_year} 學年度的獎學金配置，請先建立配置。", batch_id=batch_import.id
            )

        seq_semester = semester if semester is not None else "yearly"
        current_row = 0
        applications: List[Application] = []
        try:
            user_map = await self._get_or_create_users_bulk(
                [{"student_id": r["student_id"], "student_name": r["student_name"]} for r in parsed_rows]
            )
            for idx, row in enumerate(parsed_rows):
                current_row = row.get("row_number", idx + 2)
                user = user_map[row["student_id"]]

                # Inline sequential app_id with 'R' (renewal) suffix — same lock pattern as batch import.
                seq_stmt = (
                    select(ApplicationSequence)
                    .where(
                        and_(
                            ApplicationSequence.academic_year == academic_year,
                            ApplicationSequence.semester == seq_semester,
                        )
                    )
                    .with_for_update()
                )
                seq_record = (await self.db.execute(seq_stmt)).scalar_one_or_none()
                if not seq_record:
                    seq_record = ApplicationSequence(
                        academic_year=academic_year, semester=seq_semester, last_sequence=0
                    )
                    self.db.add(seq_record)
                    await self.db.flush()
                seq_record.last_sequence += 1
                app_id = f"{ApplicationSequence.format_app_id(academic_year, seq_semester, seq_record.last_sequence)}R"

                student_data = None
                try:
                    student_data = await self.student_service.get_student_snapshot(
                        row["student_id"], academic_year=str(academic_year), semester=semester
                    )
                except (NotFoundError, ServiceUnavailableError):
                    logger.warning("SIS snapshot unavailable for %s", row["student_id"], exc_info=True)

                # A row without a snapshot has no std_stdcode, so 造冊 hard-skips it —
                # creating an approved renewal that silently vanishes from the roster.
                # Fail the whole (all-or-nothing) batch instead (spec §6).
                if not student_data:
                    raise BatchImportError(
                        message=(
                            f"學號 {row['student_id']} 無法取得學籍資料"
                            "（SIS 不可用或查無此學號），請於學籍系統恢復後重試。"
                        ),
                        batch_id=batch_import.id,
                    )

                now = datetime.now(timezone.utc)
                application = Application(
                    app_id=app_id,
                    user_id=user.id,
                    scholarship_type_id=scholarship_type_id,
                    scholarship_configuration_id=config.id,
                    allocation_config_id=config.id,
                    scholarship_name=scholarship.name,
                    amount=config.amount,
                    sub_scholarship_type=row["sub_type"],
                    scholarship_subtype_list=[row["sub_type"]],
                    sub_type_selection_mode=scholarship.sub_type_selection_mode,
                    academic_year=academic_year,
                    semester=semester_enum,
                    is_renewal=True,
                    renewal_year=academic_year,
                    status=ApplicationStatus.approved.value,
                    review_stage=ReviewStage.quota_distributed.value,
                    quota_allocation_status="allocated",
                    approved_at=now,
                    submitted_at=now,
                    imported_by_id=batch_import.importer_id,
                    batch_import_id=batch_import.id,
                    import_source="renewal_import",
                    document_status="complete",
                    student_data=student_data,
                    submitted_form_data={
                        "postal_account": row.get("postal_account"),
                        "advisor_name": row.get("advisor_name"),
                        "advisor_nycu_id": row.get("advisor_nycu_id"),
                        "custom_fields": {},
                    },
                )
                self.db.add(application)
                applications.append(application)

            await self.db.flush()
            created_ids = [app.id for app in applications]
        except Exception as e:  # noqa: BLE001 - convert to BatchImportError after rollback
            await self.db.rollback()
            batch_import.import_status = BatchImportStatus.failed.value
            batch_import.error_summary = {"failed_at_row": current_row, "message": str(e)}
            await self.db.commit()
            raise BatchImportError(
                message=f"續領匯入失敗於第 {current_row} 行: {str(e)}", batch_id=batch_import.id
            ) from e

        return created_ids, errors
