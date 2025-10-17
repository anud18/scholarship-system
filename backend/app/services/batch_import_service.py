"""
Batch Import Service for offline application data import

Handles Excel/CSV parsing, validation, and application creation
for college staff importing offline collected student data.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceUnavailableError
from app.models.application import Application, ApplicationStatus
from app.models.application_sequence import ApplicationSequence
from app.models.batch_import import BatchImport
from app.models.enums import BatchImportStatus, Semester
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.schemas.batch_import import ApplicationDataRow, BatchImportValidationError
from app.services.student_service import StudentService

logger = logging.getLogger(__name__)


DEPT_CODE_COLUMNS = [
    "dept_code",
    "deptCode",
    "系所代碼",
    "系所代號",
    "科系代碼",
    "科系代號",
    "學系代碼",
    "學系代號",
]


def _normalize_identifier(value: Any) -> str:
    """Convert cell value to trimmed string identifier."""
    if value is None:
        return ""
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        if value.is_integer():
            value = int(value)
    return str(value).strip()


def _normalize_optional(value: Any) -> Optional[str]:
    """Convert optional cell value to trimmed string, handling NaN/None."""
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        if value.is_integer():
            value = int(value)
    normalized = str(value).strip()
    return normalized or None


class BatchImportService:
    """Service for handling batch import operations"""

    def __init__(self, db: AsyncSession, student_service: Optional[StudentService] = None):
        self.db = db
        self.student_service = student_service or StudentService()

    async def parse_excel_file(
        self, file_content: bytes, scholarship_type_id: int, academic_year: int, semester: Optional[str]
    ) -> Tuple[List[Dict[str, Any]], List[BatchImportValidationError]]:
        """
        Parse Excel/CSV file and validate data

        Args:
            file_content: File bytes
            scholarship_type_id: Scholarship type ID
            academic_year: Academic year
            semester: Semester (optional)

        Returns:
            Tuple of (parsed_data, validation_errors)
        """
        from app.models.application_field import ApplicationField
        from app.models.scholarship import ScholarshipType

        errors = []
        parsed_data = []

        try:
            # Try reading as Excel first
            df = pd.read_excel(io.BytesIO(file_content))
        except Exception:
            try:
                # Fallback to CSV
                df = pd.read_csv(io.BytesIO(file_content))
            except Exception as e:
                errors.append(
                    BatchImportValidationError(
                        row_number=0,
                        student_id=None,
                        field="file",
                        error_type="parse_error",
                        message=f"無法解析檔案: {str(e)}",
                    )
                )
                return [], errors

        # Get scholarship type for sub_type_list
        scholarship = await self.db.get(ScholarshipType, scholarship_type_id)
        if not scholarship:
            errors.append(
                BatchImportValidationError(
                    row_number=0,
                    student_id=None,
                    field="scholarship_type",
                    error_type="not_found",
                    message=f"獎學金類型 ID {scholarship_type_id} 不存在",
                )
            )
            return [], errors

        # Get custom fields configuration
        custom_fields_stmt = (
            select(ApplicationField)
            .where(ApplicationField.scholarship_type == scholarship.code)
            .where(ApplicationField.is_active)
        )
        custom_fields_result = await self.db.execute(custom_fields_stmt)
        custom_fields = custom_fields_result.scalars().all()

        # Sub-type label mapping
        sub_type_labels = {
            "國科會": "nstc",
            "教育部配合款1萬": "moe_1w",
            "教育部配合款2萬": "moe_2w",
        }

        # Add custom field mappings
        custom_field_mapping = {}
        for field in custom_fields:
            custom_field_mapping[field.field_label] = field.field_name

        # Validate required columns (check both Chinese and English names)
        required_columns_chinese = ["學號", "學生姓名"]
        required_columns_english = ["student_id", "student_name"]

        has_chinese = all(col in df.columns for col in required_columns_chinese)
        has_english = all(col in df.columns for col in required_columns_english)

        if not has_chinese and not has_english:
            errors.append(
                BatchImportValidationError(
                    row_number=0,
                    student_id=None,
                    field="columns",
                    error_type="missing_columns",
                    message=f"缺少必要欄位: {', '.join(required_columns_chinese)}",
                )
            )
            return [], errors

        # Determine which format is used
        use_chinese_columns = has_chinese

        # Track seen student IDs to detect duplicates within the file
        seen_student_ids: set = set()

        # Process each row
        for idx, row in df.iterrows():
            row_number = idx + 2  # Excel row number (header is 1)

            # Get student_id based on column format
            if use_chinese_columns:
                student_id = _normalize_identifier(row.get("學號", ""))
            else:
                student_id = _normalize_identifier(row.get("student_id", ""))

            if not student_id:
                errors.append(
                    BatchImportValidationError(
                        row_number=row_number,
                        student_id=None,
                        field="student_id",
                        error_type="missing_required",
                        message="學號不可為空",
                    )
                )
                continue

            # Check for duplicate student_id within the file
            if student_id in seen_student_ids:
                errors.append(
                    BatchImportValidationError(
                        row_number=row_number,
                        student_id=student_id,
                        field="student_id",
                        error_type="duplicate_in_file",
                        message=f"學號 {student_id} 在檔案中重複出現，每位學生在同一批次中只能有一筆申請",
                    )
                )
                continue

            # Mark this student_id as seen
            seen_student_ids.add(student_id)

            # Build application data row
            try:
                # Get values based on column format
                if use_chinese_columns:
                    data_row = {
                        "student_id": student_id,
                        "student_name": _normalize_identifier(row.get("學生姓名", "")),
                        "postal_account": _normalize_optional(row.get("郵局帳號")),
                        "advisor_name": _normalize_optional(row.get("指導教授姓名")),
                        "advisor_email": _normalize_optional(row.get("指導教授Email")),
                        "advisor_nycu_id": _normalize_optional(row.get("指導教授本校人事編號")),
                        "sub_types": [],
                        "custom_fields": {},
                    }

                    # Optional department code columns
                    for dept_col in DEPT_CODE_COLUMNS:
                        if dept_col in df.columns:
                            dept_value = _normalize_optional(row.get(dept_col))
                            if dept_value:
                                data_row["dept_code"] = dept_value
                                break

                    # Parse sub_types from Chinese column names
                    for chinese_label, sub_type_code in sub_type_labels.items():
                        if chinese_label in df.columns:
                            if row.get(chinese_label) in ["Y", "y", "是", "1", 1, True]:
                                data_row["sub_types"].append(sub_type_code)

                    # Parse custom fields from Chinese column names
                    for chinese_label, field_name in custom_field_mapping.items():
                        if chinese_label in df.columns and pd.notna(row.get(chinese_label)):
                            value = row.get(chinese_label)
                            # Convert to appropriate type
                            if isinstance(value, (int, float, bool)):
                                data_row["custom_fields"][field_name] = value
                            else:
                                data_row["custom_fields"][field_name] = str(value).strip()
                else:
                    # English column format (backward compatibility)
                    data_row = {
                        "student_id": student_id,
                        "student_name": _normalize_identifier(row.get("student_name", "")),
                        "postal_account": _normalize_optional(row.get("postal_account")),
                        "advisor_name": _normalize_optional(row.get("advisor_name")),
                        "advisor_email": _normalize_optional(row.get("advisor_email")),
                        "advisor_nycu_id": _normalize_optional(row.get("advisor_nycu_id")),
                        "sub_types": [],
                        "custom_fields": {},
                    }

                    # Optional department code columns
                    for dept_col in DEPT_CODE_COLUMNS:
                        if dept_col in df.columns:
                            dept_value = _normalize_optional(row.get(dept_col))
                            if dept_value:
                                data_row["dept_code"] = dept_value
                                break

                    # Parse sub_types from English column names (sub_type_*)
                    for col in df.columns:
                        if col.startswith("sub_type_"):
                            sub_type_code = col.replace("sub_type_", "")
                            if row.get(col) in ["Y", "y", "是", "1", 1, True]:
                                data_row["sub_types"].append(sub_type_code)

                    # Parse custom fields from English column names (custom_*)
                    for col in df.columns:
                        if col.startswith("custom_"):
                            field_name = col.replace("custom_", "")
                            if pd.notna(row.get(col)):
                                value = row.get(col)
                                if isinstance(value, (int, float, bool)):
                                    data_row["custom_fields"][field_name] = value
                                else:
                                    data_row["custom_fields"][field_name] = str(value).strip()

                # Validate using Pydantic schema and capture normalized values
                validated_row = ApplicationDataRow(**data_row)
                normalized_row = validated_row.model_dump()
                normalized_row["row_number"] = row_number
                parsed_data.append(normalized_row)

            except Exception as e:
                errors.append(
                    BatchImportValidationError(
                        row_number=row_number,
                        student_id=student_id,
                        field="row_data",
                        error_type="validation_error",
                        message=f"資料驗證失敗: {str(e)}",
                    )
                )

        return parsed_data, errors

    async def validate_college_permission(
        self, student_id: str, college_code: str, dept_code: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if student belongs to the specified college

        Args:
            student_id: Student ID
            college_code: College code (e.g., 'E', 'C', 'I', etc.)
            dept_code: Department code from import data (optional)

        Returns:
            Tuple of (is_valid, error_message)
        """
        from app.models.student import Department

        # Get student from database
        stmt = select(User).where(User.nycu_id == student_id)
        result = await self.db.execute(stmt)
        student = result.scalar_one_or_none()

        if not student:
            return False, f"查無學號 {student_id} 的使用者資料（可能尚未透過 Portal 登入本系統），將於後續確認"

        # Get student's department from raw_data JSON or dept_code column
        student_dept = None
        if student.raw_data and isinstance(student.raw_data, dict):
            student_dept = student.raw_data.get("deptCode")

        if not student_dept:
            student_dept = student.dept_code

        # Allow override from import data when existing record lacks dept information
        normalized_dept_code = _normalize_optional(dept_code)
        if not student_dept and normalized_dept_code:
            student_dept = normalized_dept_code

        if not student_dept:
            # If no dept in database, use dept_code from import data
            if not normalized_dept_code:
                return False, f"學生 {student_id} 無系所資料，且匯入資料未提供 dept_code"
            student_dept = normalized_dept_code

        # Query department from database to get academy_code
        dept_stmt = select(Department).where(Department.code == student_dept)
        dept_result = await self.db.execute(dept_stmt)
        department = dept_result.scalar_one_or_none()

        if not department:
            return False, f"查無系所代碼 {student_dept} 的資料"

        if not department.academy_code:
            return False, f"系所 {student_dept} 未設定學院代碼"

        student_college = department.academy_code

        if student_college != college_code:
            return (
                False,
                f"學生 {student_id} 所屬學院 ({student_college}) 與匯入學院 ({college_code}) 不符",
            )

        return True, None

    async def check_duplicate_application(
        self, student_id: str, scholarship_type_id: int, academic_year: int, semester: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if student already has an application for this scholarship

        Returns:
            Tuple of (is_duplicate, error_message)
        """
        # Find user by student ID
        stmt = select(User).where(User.nycu_id == student_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return False, None  # No user = no duplicate

        # Check for existing application
        app_stmt = (
            select(Application)
            .where(
                Application.user_id == user.id,
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.semester == semester,
            )
            .limit(1)
        )
        result = await self.db.execute(app_stmt)
        existing_app = result.scalar_one_or_none()

        if existing_app:
            return True, f"學生 {student_id} 已有此獎學金的申請記錄 (APP-{existing_app.id})"

        return False, None

    async def bulk_validate_permissions_and_duplicates(
        self,
        student_ids: List[str],
        college_code: str,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        student_dept_map: Optional[Dict[str, Optional[str]]] = None,
        student_row_map: Optional[Dict[str, int]] = None,
    ) -> Tuple[Dict[str, Tuple[bool, Optional[str]]], Dict[str, Tuple[bool, Optional[str]]], List[Dict[str, Any]],]:
        """
        Bulk validate college permissions and check duplicates for multiple students

        Returns:
            Tuple of (permission_results, duplicate_results, warnings)
            Each dict maps student_id to (is_valid/is_duplicate, error_message)
        """
        from app.models.student import Academy, Department

        permission_results: Dict[str, Tuple[bool, Optional[str]]] = {
            student_id: (True, None) for student_id in student_ids
        }
        duplicate_results: Dict[str, Tuple[bool, Optional[str]]] = {}
        warnings: List[Dict[str, Any]] = []
        student_dept_map = student_dept_map or {}
        student_row_map = student_row_map or {}
        normalized_semester_str = _normalize_optional(semester)
        normalized_semester_enum: Optional[Semester] = None
        if normalized_semester_str:
            try:
                normalized_semester_enum = Semester(normalized_semester_str)
            except ValueError:
                normalized_semester_enum = None

        def add_warning(
            student_id: Optional[str],
            warning_type: str,
            message: str,
            field: str = "department",
        ) -> None:
            warnings.append(
                {
                    "row_number": student_row_map.get(student_id) if student_id else None,
                    "student_id": student_id,
                    "field": field,
                    "warning_type": warning_type,
                    "message": message,
                }
            )

        dept_cache: Dict[str, Optional[Department]] = {}
        academy_cache: Dict[str, Optional[Academy]] = {}

        async def get_department_by_code(code: str) -> Optional[Department]:
            if code not in dept_cache:
                dept_stmt = select(Department).where(Department.code == code)
                dept_result = await self.db.execute(dept_stmt)
                dept_cache[code] = dept_result.scalar_one_or_none()
            return dept_cache[code]

        async def get_academy_by_code(code: str) -> Optional[Academy]:
            if code not in academy_cache:
                academy_stmt = select(Academy).where(Academy.code == code)
                academy_result = await self.db.execute(academy_stmt)
                academy_cache[code] = academy_result.scalar_one_or_none()
            return academy_cache[code]

        # Batch query: Get all students by student IDs
        students_stmt = select(User).where(User.nycu_id.in_(student_ids))
        students_result = await self.db.execute(students_stmt)
        students = students_result.scalars().all()
        student_map = {s.nycu_id: s for s in students}

        # Find missing students
        for student_id in student_ids:
            if student_id not in student_map:
                dept_code = _normalize_optional(student_dept_map.get(student_id))
                if not dept_code:
                    add_warning(
                        student_id, "student_not_in_system", f"查無學號 {student_id} 的使用者資料（可能尚未透過 Portal 登入本系統），將於後續確認"
                    )
                    duplicate_results[student_id] = (False, None)
                    continue

                dept = await get_department_by_code(dept_code)

                if not dept:
                    add_warning(
                        student_id,
                        "department_not_found",
                        f"系所代碼 {dept_code} 不存在，請後續確認學生系所資訊。",
                    )
                elif college_code and dept.academy_code != college_code:
                    # Get academy names for better error message
                    dept_academy = await get_academy_by_code(dept.academy_code) if dept.academy_code else None
                    current_academy = await get_academy_by_code(college_code)
                    dept_academy_name = dept_academy.name if dept_academy else dept.academy_code
                    current_academy_name = current_academy.name if current_academy else college_code

                    add_warning(
                        student_id,
                        "college_mismatch_local",
                        f"學生 {student_id} 的系所 ({dept.name}) 隸屬 {dept_academy_name}，與目前學院 {current_academy_name} 不符。",
                    )

                duplicate_results[student_id] = (False, None)

        # Get department info for permission validation
        for student_id, student in student_map.items():
            # Get student's department from raw_data JSON or dept_code column
            if student.raw_data and isinstance(student.raw_data, dict):
                student_dept = student.raw_data.get("deptCode") or student.dept_code
            else:
                student_dept = student.dept_code

            if not student_dept:
                fallback_dept = _normalize_optional(student_dept_map.get(student_id))
                if fallback_dept:
                    student_dept = fallback_dept
                else:
                    add_warning(
                        student_id,
                        "missing_department_local",
                        f"學生 {student_id} 無系所資料，請後續確認。",
                    )
                    continue

            dept = await get_department_by_code(student_dept)

            if not dept:
                add_warning(
                    student_id,
                    "department_not_found",
                    f"系所代碼 {student_dept} 不存在，請後續確認。",
                )
                continue

            # Validate college permission
            if college_code and dept.academy_code != college_code:
                # Get academy names for better error message
                dept_academy = await get_academy_by_code(dept.academy_code) if dept.academy_code else None
                current_academy = await get_academy_by_code(college_code)
                dept_academy_name = dept_academy.name if dept_academy else dept.academy_code
                current_academy_name = current_academy.name if current_academy else college_code

                add_warning(
                    student_id,
                    "college_mismatch_local",
                    f"學生 {student_id} 的系所 ({dept.name}) 隸屬 {dept_academy_name}，與目前學院 {current_academy_name} 不符。",
                )

        # Query student API for latest department info
        api_codes: Dict[str, str] = {}
        if getattr(self.student_service, "api_enabled", False):
            api_failed = False
            for student_id in student_ids:
                try:
                    api_data = await self.student_service.get_student_basic_info(student_id)
                except ServiceUnavailableError:
                    if not api_failed:
                        add_warning(
                            None,
                            "student_api_unavailable",
                            "學籍系統目前不可用，已跳過即時系所驗證。",
                        )
                        api_failed = True
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("Student API unexpected error for %s: %s", student_id, exc)
                    add_warning(
                        student_id,
                        "student_api_error",
                        f"查詢學生 {student_id} 的學籍資料時發生錯誤，請後續確認。",
                    )
                    continue

                if not api_data:
                    add_warning(
                        student_id,
                        "student_api_not_found",
                        f"學籍系統查無學號 {student_id}，請後續確認。",
                    )
                    continue

                dep_code = _normalize_optional(api_data.get("std_depno"))
                if not dep_code:
                    add_warning(
                        student_id,
                        "student_api_missing_depno",
                        f"學籍系統回傳的學生 {student_id} 缺少系所代碼，請後續確認。",
                    )
                    continue

                api_codes[student_id] = dep_code.upper()

        # Compare API department data with college
        if api_codes:
            api_dept_stmt = select(Department).where(Department.code.in_(list(set(api_codes.values()))))
            api_dept_result = await self.db.execute(api_dept_stmt)
            api_depts = api_dept_result.scalars().all()
            api_dept_lookup = {dept.code: dept for dept in api_depts}

            for student_id, dept_code in api_codes.items():
                dept = api_dept_lookup.get(dept_code)
                if not dept:
                    add_warning(
                        student_id,
                        "student_api_department_unknown",
                        f"學籍系統回傳系所代碼 {dept_code} 未在系所資料表中，請後續確認。",
                    )
                    continue

                if college_code and dept.academy_code != college_code:
                    # Get academy names for better error message
                    dept_academy = await get_academy_by_code(dept.academy_code) if dept.academy_code else None
                    current_academy = await get_academy_by_code(college_code)
                    dept_academy_name = dept_academy.name if dept_academy else dept.academy_code
                    current_academy_name = current_academy.name if current_academy else college_code

                    add_warning(
                        student_id,
                        "college_mismatch_api",
                        f"學籍系統顯示學生 {student_id} 的系所 ({dept.name}) 隸屬 {dept_academy_name}，與目前學院 {current_academy_name} 不符。",
                    )

        # Batch query: Check for duplicate applications
        user_ids = [s.id for s in students]
        if user_ids:
            duplicates_stmt = select(Application).where(
                Application.user_id.in_(user_ids),
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
            )

            if normalized_semester_enum is None:
                duplicates_stmt = duplicates_stmt.where(Application.semester.is_(None))
            else:
                duplicates_stmt = duplicates_stmt.where(Application.semester == normalized_semester_enum)

            duplicates_result = await self.db.execute(duplicates_stmt)
            duplicate_apps = duplicates_result.scalars().all()

            # Map user_id to application
            user_id_to_app = {app.user_id: app for app in duplicate_apps}

            # Check each student for duplicates
            for student_id, student in student_map.items():
                if student.id in user_id_to_app:
                    app = user_id_to_app[student.id]
                    duplicate_results[student_id] = (
                        True,
                        f"學生 {student_id} 已有此獎學金的申請記錄 (APP-{app.id})",
                    )
                else:
                    duplicate_results[student_id] = (False, None)

        # Ensure duplicates entry exists for students not in DB
        for student_id in student_ids:
            duplicate_results.setdefault(student_id, (False, None))

        return permission_results, duplicate_results, warnings

    async def create_batch_import_record(
        self,
        importer_id: int,
        college_code: str,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        file_name: str,
        total_records: int,
    ) -> BatchImport:
        """Create a batch import record with 7-day TTL for sensitive data"""
        from datetime import timedelta

        # Set data expiration to 7 days from now for auto-cleanup
        data_expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        batch_import = BatchImport(
            importer_id=importer_id,
            college_code=college_code,
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
            file_name=file_name,
            total_records=total_records,
            import_status=BatchImportStatus.pending.value,
            data_expires_at=data_expires_at,
        )
        self.db.add(batch_import)
        await self.db.flush()
        return batch_import

    async def _get_or_create_users_bulk(self, parsed_data: List[Dict[str, Any]]) -> Dict[str, User]:
        """
        Bulk fetch existing users and create missing ones.
        Returns dict mapping student_id to User object.
        """
        # Extract all student IDs
        student_ids = [row["student_id"] for row in parsed_data]

        # Bulk fetch existing users
        stmt = select(User).where(User.nycu_id.in_(student_ids))
        result = await self.db.execute(stmt)
        existing_users = result.scalars().all()

        # Map existing users by nycu_id
        user_map = {user.nycu_id: user for user in existing_users}

        # Identify missing users
        missing_student_ids = set(student_ids) - set(user_map.keys())

        # Bulk create missing users
        if missing_student_ids:
            new_users = []
            for row in parsed_data:
                student_id = row["student_id"]
                if student_id in missing_student_ids:
                    new_user = User(
                        nycu_id=student_id,
                        name=row["student_name"],
                        email=f"{student_id}@nycu.edu.tw",
                        user_type="student",
                        role="student",
                        dept_code=row.get("dept_code"),
                        raw_data={
                            "imported_from_batch": True,
                            "batch_import_data": row,
                        },
                    )
                    new_users.append(new_user)
                    self.db.add(new_user)

            # Flush to get IDs
            await self.db.flush()

            # Update user_map with new users
            for user in new_users:
                user_map[user.nycu_id] = user

        return user_map

    async def create_applications_from_batch(
        self,
        batch_import: BatchImport,
        parsed_data: List[Dict[str, Any]],
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
    ) -> Tuple[List[int], List[BatchImportValidationError]]:
        """
        Create Application records from parsed batch data with transaction safety.

        Uses bulk operations for performance:
        1. Bulk fetch all users
        2. Bulk create missing users
        3. Bulk create applications

        Uses all-or-nothing transaction strategy: if ANY operation fails,
        the entire batch is rolled back.

        Returns:
            Tuple of (created_application_ids, errors)
        """
        from app.core.exceptions import BatchImportError

        created_ids = []
        errors = []

        # Get scholarship type
        scholarship = await self.db.get(ScholarshipType, scholarship_type_id)
        if not scholarship:
            raise BatchImportError(
                message=f"獎學金類型 ID {scholarship_type_id} 不存在",
                batch_id=batch_import.id,
            )

        # Begin transaction - all operations will be rolled back if any fails
        current_row = 0
        try:
            # Step 1: Bulk get/create users
            user_map = await self._get_or_create_users_bulk(parsed_data)

            # Step 2: Bulk create applications
            applications = []
            for idx, row_data in enumerate(parsed_data):
                student_id = row_data["student_id"]
                current_row = idx + 2  # Track current row for error reporting

                user = user_map[student_id]

                # Generate app_id using the shared sequence, and append 'U' for upload/batch.
                # This logic is adapted from ApplicationService._generate_app_id
                temp_semester = semester
                if temp_semester is None:
                    temp_semester = "yearly"

                # Lock the sequence record for the duration of this transaction
                stmt = (
                    select(ApplicationSequence)
                    .where(
                        and_(
                            ApplicationSequence.academic_year == academic_year,
                            ApplicationSequence.semester == temp_semester,
                        )
                    )
                    .with_for_update()
                )

                result = await self.db.execute(stmt)
                seq_record = result.scalar_one_or_none()

                # Create sequence record if it doesn't exist
                if not seq_record:
                    seq_record = ApplicationSequence(
                        academic_year=academic_year, semester=temp_semester, last_sequence=0
                    )
                    self.db.add(seq_record)
                    await self.db.flush()  # Flush to get the record in the session

                # Increment sequence
                seq_record.last_sequence += 1
                sequence_num = seq_record.last_sequence

                # Format and return app_id
                # NOTE: We do NOT commit here. The lock is held for the entire batch transaction
                # to ensure atomicity. This will block online applications during the import.
                base_app_id = ApplicationSequence.format_app_id(academic_year, temp_semester, sequence_num)
                app_id = f"{base_app_id}U"

                # Create application
                student_payload = {
                    "nycu_id": student_id,
                    "name": row_data["student_name"],
                }
                if row_data.get("dept_code"):
                    student_payload["dept_code"] = row_data.get("dept_code")
                if batch_import.college_code:
                    student_payload["college_code"] = batch_import.college_code

                application = Application(
                    app_id=app_id,
                    user_id=user.id,
                    scholarship_type_id=scholarship_type_id,
                    scholarship_name=scholarship.name,
                    amount=None,  # Amount is now per sub-type in ScholarshipSubTypeConfig
                    main_scholarship_type=scholarship.get_main_type_from_code(),
                    sub_scholarship_type=row_data.get("sub_types", [None])[0]
                    if row_data.get("sub_types")
                    else "GENERAL",
                    scholarship_subtype_list=row_data.get("sub_types", []),
                    sub_type_selection_mode=scholarship.sub_type_selection_mode,
                    academic_year=academic_year,
                    semester=semester,
                    status=ApplicationStatus.under_review.value,
                    imported_by_id=batch_import.importer_id,
                    batch_import_id=batch_import.id,
                    import_source="batch_import",
                    document_status="pending_documents",
                    submitted_at=datetime.now(timezone.utc),
                    student_data=student_payload,
                    submitted_form_data={
                        "postal_account": row_data.get("postal_account"),
                        "advisor_name": row_data.get("advisor_name"),
                        "advisor_email": row_data.get("advisor_email"),
                        "advisor_nycu_id": row_data.get("advisor_nycu_id"),
                        "custom_fields": row_data.get("custom_fields", {}),
                    },
                )
                applications.append(application)
                self.db.add(application)

            # Flush all applications at once
            await self.db.flush()

            # Collect created IDs
            created_ids = [app.id for app in applications]

        except Exception as e:
            # Rollback all changes on any error
            await self.db.rollback()

            # Update batch status to failed
            batch_import.import_status = BatchImportStatus.failed.value
            batch_import.error_summary = {
                "total_errors": 1,
                "error_type": "transaction_rollback",
                "failed_at_row": current_row,
                "message": f"批次匯入失敗於第 {current_row} 行，所有變更已回復: {str(e)}",
            }
            await self.db.commit()

            raise BatchImportError(
                message=f"批次匯入失敗於第 {current_row} 行: {str(e)}",
                batch_id=batch_import.id,
            )

        return created_ids, errors

    async def update_batch_import_status(
        self,
        batch_import: BatchImport,
        success_count: int,
        failed_count: int,
        errors: List[BatchImportValidationError],
        status: str = "completed",
    ):
        """Update batch import record with results"""
        batch_import.success_count = success_count
        batch_import.failed_count = failed_count
        # Status string will be automatically converted to enum value by SQLAlchemy
        batch_import.import_status = status

        if errors:
            batch_import.error_summary = {
                "total_errors": len(errors),
                "errors": [
                    {
                        "row": e.row_number,
                        "student_id": e.student_id,
                        "field": e.field,
                        "type": e.error_type,
                        "message": e.message,
                    }
                    for e in errors
                ],
            }

        await self.db.commit()

    async def cleanup_expired_data(self) -> int:
        """
        Clean up expired parsed_data from batch imports.

        Deletes parsed_data JSON field from batch imports where:
        - data_expires_at is in the past
        - parsed_data is not None

        Returns:
            Number of records cleaned up
        """
        # Find expired batch imports with data
        stmt = select(BatchImport).where(
            BatchImport.data_expires_at <= datetime.now(timezone.utc), BatchImport.parsed_data.isnot(None)
        )

        result = await self.db.execute(stmt)
        expired_batches = result.scalars().all()

        count = 0
        for batch in expired_batches:
            # Clear sensitive parsed_data
            batch.parsed_data = None
            count += 1

        if count > 0:
            await self.db.commit()

        return count
