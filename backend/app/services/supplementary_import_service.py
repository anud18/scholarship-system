"""Supplementary import service — a college creates applications for new students.

補充匯入 is the college's own way to submit applications on a student's behalf.
It replaced 批次匯入 for colleges and therefore reads the SAME workbook: parsing,
the sub-type checkmark columns, the advisor trio and the custom-field mapping all
come from BatchImportService, so a file downloaded from either panel imports
through either panel. What differs is only the surrounding flow — one step
instead of upload/preview/confirm, scoped to the caller's own college, and no
BatchImport record.

The applications it creates are ordinary submitted applications: no rank, and no
CollegeRankingItem. 名次 is decided later by the ordinary college ranking flow,
exactly as it is for every other applicant.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SupplementaryImportService:
    """Handles all logic for the college's 補充匯入."""

    def __init__(self, db, student_service=None):
        from app.services.batch_import_service import BatchImportService
        from app.services.student_service import StudentService

        self.db = db
        self.student_service = student_service or StudentService()
        # Same reader as 批次匯入 — see module docstring.
        self.batch_service = BatchImportService(db)

    async def parse_file(
        self,
        file_content: bytes,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Parse the uploaded workbook, returning (rows, human-readable errors).

        Delegates to the batch-import parser so the accepted file is byte-for-byte
        the 批次匯入 format. Errors are flattened to strings because 補充匯入 is a
        single-shot import with no preview screen to render structured rows into.
        """
        rows, validation_errors = await self.batch_service.parse_excel_file(
            file_content=file_content,
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
        )

        messages: List[str] = []
        for err in validation_errors:
            row_number = getattr(err, "row_number", None) or 0
            message = getattr(err, "message", str(err))
            messages.append(f"第 {row_number} 列：{message}" if row_number else message)

        # 續領 has its own admin-only import; a renewal row here would silently
        # become a brand-new application under a renewal year.
        renewal_ids = [r["student_id"] for r in rows if r.get("is_renewal")]
        if renewal_ids:
            messages.append("補充匯入僅供新申請學生使用，續領請由管理員以「匯入續領生」處理：" + "、".join(renewal_ids))

        return rows, messages

    # -------- DB + SIS helpers --------

    async def validate_no_duplicate_applications(
        self,
        rows: List[Dict[str, Any]],
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
    ) -> List[str]:
        """Return list of student_ids that already have an application for this scholarship/year/semester."""
        from sqlalchemy import select, and_, or_
        from app.models.application import Application
        from app.models.user import User

        student_ids = [r["student_id"] for r in rows]
        if not student_ids:
            return []

        user_stmt = select(User.id, User.nycu_id).where(User.nycu_id.in_(student_ids))
        user_result = await self.db.execute(user_stmt)
        nycu_to_user_id = {nycu_id: uid for uid, nycu_id in user_result.all()}

        if not nycu_to_user_id:
            return []

        user_ids = list(nycu_to_user_id.values())

        if semester == "yearly":
            sem_cond = or_(
                Application.semester.is_(None),
                Application.semester == "yearly",
            )
        else:
            sem_cond = Application.semester == semester

        app_stmt = select(Application.user_id).where(
            and_(
                Application.user_id.in_(user_ids),
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                sem_cond,
                Application.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(app_stmt)
        conflicting_user_ids = {row[0] for row in result.all()}

        user_id_to_nycu = {v: k for k, v in nycu_to_user_id.items()}
        return [user_id_to_nycu[uid] for uid in conflicting_user_ids if uid in user_id_to_nycu]

    async def fetch_student_data_bulk(
        self,
        student_ids: List[str],
        academic_year: int,
        semester: Optional[str],
    ) -> Tuple[Dict[str, dict], List[str], List[str]]:
        """Fetch student_data from SIS API for each student_id.

        Returns (data_map, missing_ids, errored_ids).

        `missing_ids` are 學號 the SIS positively does not know — a data problem the
        college can fix. `errored_ids` failed for any other reason (timeout, 5xx,
        transport): telling the operator those 學號 "do not exist" would send them
        hunting for a typo in a perfectly correct number, so the caller must report
        them differently. Raises ValueError if the SIS API is not enabled at all.

        Lookups run concurrently (bounded) via the shared batch-import helper —
        a sequential loop took 20-45s for a full sheet and the Next.js proxy
        reset the socket before it finished (issue #1172).
        """
        from app.core.exceptions import NotFoundError
        from app.services.batch_import_service import _fetch_per_student

        if not getattr(self.student_service, "api_enabled", False):
            raise ValueError("學生 API 未啟用，無法驗證學生資料")

        results = await _fetch_per_student(
            student_ids,
            lambda student_id: self.student_service.get_student_snapshot(
                student_id,
                academic_year=str(academic_year),
                semester=semester,
            ),
        )

        data_map: Dict[str, dict] = {}
        missing: List[str] = []
        errored: List[str] = []

        for student_id in student_ids:
            data = results.get(student_id)
            if isinstance(data, NotFoundError):
                missing.append(student_id)
            elif isinstance(data, BaseException):
                logger.warning("SIS API error for %s: %s", student_id, data, exc_info=data)
                errored.append(student_id)
            else:
                data_map[student_id] = data

        return data_map, missing, errored

    async def find_or_create_users(self, student_data_map: Dict[str, dict]) -> Dict[str, object]:
        """Return {student_id: User} — creates User if not found."""
        from sqlalchemy import select
        from app.models.user import User, UserRole, UserType

        student_ids = list(student_data_map.keys())
        if not student_ids:
            return {}

        stmt = select(User).where(User.nycu_id.in_(student_ids))
        result = await self.db.execute(stmt)
        user_map: Dict[str, "User"] = {u.nycu_id: u for u in result.scalars().all()}

        for student_id, sis_data in student_data_map.items():
            if student_id in user_map:
                continue
            new_user = User(
                nycu_id=student_id,
                name=sis_data.get("std_cname") or student_id,
                email=sis_data.get("com_email"),
                user_type=UserType.student,
                role=UserRole.student,
                dept_code=sis_data.get("std_depno"),
            )
            self.db.add(new_user)
            await self.db.flush()
            user_map[student_id] = new_user

        return user_map

    async def upsert_user_profiles(
        self,
        user_map: Dict[str, object],
        rows: List[Dict[str, Any]],
    ) -> Dict[int, object]:
        """Write 郵局帳號 + the advisor trio to each student's UserProfile.

        Delegates to the batch-import upsert so the overwrite policy (a non-empty
        cell wins, a blank cell preserves) is identical across both import paths.
        Crucially it stores 指導教授本校人事編號, which is what makes the professor
        auto-assignment in create_applications able to resolve at all.

        Returns {user_id: UserProfile} so the caller can hand the already-loaded
        profile to assign_professor_from_profile instead of re-SELECTing it.
        """
        row_map = {r["student_id"]: r for r in rows}
        profile_map: Dict[int, object] = {}

        for student_id, user in user_map.items():
            row = row_map.get(student_id)
            if not row:
                continue
            profile_map[user.id] = await self.batch_service.upsert_user_profile(user, row)

        await self.db.flush()
        return profile_map

    async def create_applications(
        self,
        rows: List[Dict[str, Any]],
        user_map: Dict[str, object],
        student_data_map: Dict[str, dict],
        scholarship_configuration,  # ScholarshipConfiguration ORM object
        importer_id: int,
        profile_map: Optional[Dict[int, object]] = None,
    ) -> Tuple[int, List[str]]:
        """Create one submitted Application per imported row.

        Returns (created_count, student_ids whose 指導教授 could not be resolved).

        No CollegeRankingItem is created and no rank is assigned: an imported
        student joins the ordinary applicant pool and is ranked by the normal
        college ranking flow, exactly like a self-submitting student.

        `scholarship_configuration` is required: roster rule validation loads
        that period's rules via applications.scholarship_configuration_id, so
        an application created without it gets excluded from 造冊 with
        「未關聯獎學金配置」(issue #1213).
        """
        from app.core.exceptions import ValidationError
        from app.models.application import Application
        from app.models.enums import Semester
        from app.services.application_builder import (
            assign_professor_from_profile,
            build_submitted_application_values,
            derive_sub_scholarship_type,
            generate_app_id,
            validate_sub_type_for_submission,
        )

        if scholarship_configuration is None:
            raise ValueError(
                "找不到對應的獎學金配置，無法補充匯入（applications.scholarship_configuration_id "
                "不可為空，否則造冊時會被排除）。請先建立該學年/學期的獎學金配置。"
            )

        if not rows:
            return 0, []

        cfg = scholarship_configuration
        scholarship = cfg.scholarship_type
        profile_map = profile_map or {}

        # ScholarshipConfiguration.semester is an Enum column; a yearly cycle stores
        # NULL there and Application.semester must stay NULL too. The app-id sequence
        # keys on the string "yearly" instead (see ApplicationSequence.format_app_id).
        # getattr(..., "value", ...) tolerates both the enum member a DB load returns
        # and a bare string an in-memory fixture may carry.
        raw_semester = getattr(cfg.semester, "value", cfg.semester)
        semester_value = None if raw_semester in (None, "", Semester.yearly.value) else raw_semester
        sequence_semester = semester_value or "yearly"

        # Shared submitted-application invariants (status/status_name/review_stage/
        # submitted_at/amount/scholarship_name) — same source as the student and
        # batch-import paths; one shared timestamp for the whole import is intended.
        submitted_values = build_submitted_application_values(scholarship, cfg)

        # Custom-field definitions are identical for the whole import — fetch once
        # (the batch path does the same) and reuse for every row.
        field_definitions = await self.batch_service.fetch_field_definitions(scholarship.code)

        created = 0
        unresolved_professors: List[str] = []
        for row in rows:
            student_id = row["student_id"]
            user = user_map.get(student_id)
            if not user:
                continue

            sis_data = student_data_map.get(student_id, {})

            # sub_types already carry the shared preference ordering (moe_1w first)
            # applied by the batch parser — do not re-order here.
            sub_types = list(row.get("sub_types") or [])
            sub_scholarship_type = derive_sub_scholarship_type(sub_types)
            try:
                validate_sub_type_for_submission(scholarship, sub_scholarship_type)
            except ValidationError as exc:
                raise ValidationError(f"學號 {student_id}：{exc.message}") from exc

            # commit=False keeps the sequence row locked for the whole import so it
            # stays atomic — same trade-off the batch-import path makes.
            app_id = await generate_app_id(self.db, cfg.academic_year, sequence_semester, commit=False)

            submitted_form_data = self.batch_service.build_submitted_form_data(
                field_definitions, row.get("custom_fields") or {}
            )

            # scholarship_subtype_list is what the manual-distribution panel reads
            # as `applied_sub_types`; sub_type_preferences is the ordered preference
            # list used by allocation logic. Both come from the checkmark columns so
            # admin can see + distribute these students. sub_scholarship_type must
            # reflect the first preference — roster rule validation selects rule sets
            # by it, and the default "general" would pick the wrong rules.
            app = Application(
                app_id=app_id,
                user_id=user.id,
                scholarship_type_id=cfg.scholarship_type_id,
                scholarship_configuration_id=cfg.id,
                scholarship_name=submitted_values["scholarship_name"],
                amount=submitted_values["amount"],
                academic_year=cfg.academic_year,
                semester=semester_value,
                status=submitted_values["status"],
                status_name=submitted_values["status_name"],
                review_stage=submitted_values["review_stage"],
                submitted_at=submitted_values["submitted_at"],
                sub_type_selection_mode=scholarship.sub_type_selection_mode,
                student_data=sis_data,
                sub_scholarship_type=sub_scholarship_type,
                scholarship_subtype_list=sub_types,
                sub_type_preferences=sub_types or None,
                submitted_form_data=submitted_form_data,
                imported_by_id=importer_id,
                import_source="supplementary_import",
                document_status="pending_documents",
            )
            self.db.add(app)
            await self.db.flush()

            # Professor linkage is what makes the application visible in the
            # professor review queue (it filters on Application.professor_id);
            # without it the student is stuck at 教授審核中 forever.
            professor = await assign_professor_from_profile(self.db, app, user.id, profile=profile_map.get(user.id))
            if professor is None:
                unresolved_professors.append(student_id)

            created += 1

        await self.db.flush()
        return created, unresolved_professors
