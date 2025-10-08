"""
Batch Import Service for offline application data import

Handles Excel/CSV parsing, validation, and application creation
for college staff importing offline collected student data.
"""

import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.batch_import import BatchImport
from app.models.enums import BatchImportStatus
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.schemas.batch_import import ApplicationDataRow, BatchImportValidationError


class BatchImportService:
    """Service for handling batch import operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

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
            .where(ApplicationField.is_active == True)
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

        # Process each row
        for idx, row in df.iterrows():
            row_number = idx + 2  # Excel row number (header is 1)

            # Get student_id based on column format
            if use_chinese_columns:
                student_id = str(row.get("學號", "")).strip()
            else:
                student_id = str(row.get("student_id", "")).strip()

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

            # Build application data row
            try:
                # Get values based on column format
                if use_chinese_columns:
                    data_row = {
                        "student_id": student_id,
                        "student_name": str(row.get("學生姓名", "")).strip(),
                        "postal_account": (str(row.get("郵局帳號", "")).strip() if pd.notna(row.get("郵局帳號")) else None),
                        "sub_types": [],
                        "custom_fields": {},
                    }

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
                        "student_name": str(row.get("student_name", "")).strip(),
                        "postal_account": (
                            str(row.get("postal_account", "")).strip() if pd.notna(row.get("postal_account")) else None
                        ),
                        "sub_types": [],
                        "custom_fields": {},
                    }

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

                # Validate using Pydantic schema
                ApplicationDataRow(**data_row)
                parsed_data.append(data_row)

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
            return False, f"查無學號 {student_id} 的學生資料"

        # Get student's department from raw_data JSON or dept_code column
        if student.raw_data and isinstance(student.raw_data, dict):
            student_dept = student.raw_data.get("deptCode") or student.dept_code
        else:
            student_dept = student.dept_code

        if not student_dept:
            # If no dept in database, use dept_code from import data
            if not dept_code:
                return False, f"學生 {student_id} 無系所資料，且匯入資料未提供 dept_code"
            student_dept = dept_code

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

                # Generate app_id
                app_id = f"APP-{academic_year}-{ApplicationStatus.submitted.value[:3].upper()}-{user.id:06d}"

                # Create application
                application = Application(
                    app_id=app_id,
                    user_id=user.id,
                    scholarship_type_id=scholarship_type_id,
                    scholarship_name=scholarship.name,
                    amount=scholarship.amount,
                    main_scholarship_type=scholarship.main_type,
                    sub_scholarship_type=row_data.get("sub_types", [None])[0]
                    if row_data.get("sub_types")
                    else "GENERAL",
                    scholarship_subtype_list=row_data.get("sub_types", []),
                    sub_type_selection_mode=scholarship.sub_type_selection_mode,
                    academic_year=academic_year,
                    semester=semester,
                    status=ApplicationStatus.submitted.value,
                    imported_by_id=batch_import.importer_id,
                    batch_import_id=batch_import.id,
                    import_source="batch_import",
                    document_status="pending_documents",
                    submitted_at=datetime.now(timezone.utc),
                    student_data={"nycu_id": student_id, "name": row_data["student_name"]},
                    submitted_form_data={
                        "postal_account": row_data.get("postal_account"),
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
