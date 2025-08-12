"""
Application service for scholarship application management
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.orm import selectinload, joinedload

from app.core.exceptions import (
    NotFoundError, ConflictError, ValidationError, 
    BusinessLogicError, AuthorizationError
)
from app.models.user import User, UserRole
from app.models.application import Application, ApplicationStatus, ApplicationReview, ProfessorReview, ProfessorReviewItem, Semester
from app.models.scholarship import ScholarshipType, SubTypeSelectionMode
from app.schemas.application import (
    ApplicationCreate, ApplicationUpdate, ApplicationResponse,
    ApplicationListResponse, ApplicationStatusUpdate,
    ApplicationReviewCreate, ApplicationReviewResponse, ApplicationFormData,
    StudentDataSchema, StudentFinancialInfo, SupervisorInfo
)
from app.services.email_service import EmailService
from app.services.minio_service import minio_service
from app.services.student_service import StudentService

logger = logging.getLogger(__name__)


async def get_student_data_from_user(user: User) -> Optional[Dict[str, Any]]:
    """Get student data from external API using user's nycu_id"""
    if user.role != UserRole.STUDENT or not user.nycu_id:
        return None
    
    student_service = StudentService()
    return await student_service.get_student_basic_info(user.nycu_id)


class ApplicationService:
    """Application management service"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.emailService = EmailService()
        self.student_service = StudentService()
    
    def _serialize_for_json(self, data: Any) -> Any:
        """Serialize data for JSON response"""
        if isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, list):
            return [self._serialize_for_json(item) for item in data]
        elif isinstance(data, dict):
            return {k: self._serialize_for_json(v) for k, v in data.items()}
        return data
    
    def _get_student_id_from_user(self, user: User) -> Optional[str]:
        """
        Get student ID from user (using nycu_id)
        
        The student_id in our system is the user's nycu_id (string format)
        """
        if not user or not user.nycu_id:
            return None
        return user.nycu_id
    
    async def _build_application_response(self, application: Application, user: Optional[User] = None) -> ApplicationResponse:
        """
        Build ApplicationResponse from Application model
        """
        # If user is not provided, try to load it from the relationship
        if not user and hasattr(application, 'student') and application.student:
            user = application.student
        elif not user:
            # Load user from database
            stmt = select(User).where(User.id == application.user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
        
        # Integrate file data from submitted_form_data.documents
        integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}
        
        return ApplicationResponse(
            id=application.id,
            app_id=application.app_id,
            user_id=application.user_id,
            student_id=self._get_student_id_from_user(user) if user else None,
            scholarship_type_id=application.scholarship_type_id,
            scholarship_subtype_list=application.scholarship_subtype_list or [],
            status=application.status,
            status_name=application.status_name,
            is_renewal=application.is_renewal,
            academic_year=application.academic_year,
            semester=self._convert_semester_to_string(application.semester),
            student_data=application.student_data or {},
            submitted_form_data=integrated_form_data,
            agree_terms=application.agree_terms,
            professor_id=application.professor_id,
            reviewer_id=application.reviewer_id,
            final_approver_id=application.final_approver_id,
            review_score=application.review_score,
            review_comments=application.review_comments,
            rejection_reason=application.rejection_reason,
            submitted_at=application.submitted_at,
            reviewed_at=application.reviewed_at,
            approved_at=application.approved_at,
            created_at=application.created_at,
            updated_at=application.updated_at,
            meta_data=application.meta_data
        )
    
    def _convert_semester_to_string(self, semester) -> Optional[str]:
        """
        Convert semester to string format for schema validation
        """
        if semester is None:
            return None
        
        # If it's already a string, return as is
        if isinstance(semester, str):
            return semester
        
        # If it's an enum or has a value attribute, get the value
        if hasattr(semester, 'value'):
            return str(semester.value)
        
        # Otherwise convert to string
        return str(semester)
    
    def _generate_app_id(self) -> str:
        """Generate unique application ID"""
        year = datetime.now().year
        random_suffix = str(uuid.uuid4().int)[-6:]
        return f"APP-{year}-{random_suffix}"
    
    async def _validate_student_eligibility(
        self, 
        student_data: Dict[str, Any], 
        scholarship_type: str,
        application_data: ApplicationCreate
    ) -> None:
        """Validate student eligibility for scholarship"""
        # Get scholarship type configuration
        stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
        result = await self.db.execute(stmt)
        scholarship = result.scalar_one_or_none()
        
        if not scholarship:
            raise NotFoundError("Scholarship type", scholarship_type)
        
        if not scholarship.is_active:
            raise ValidationError("Scholarship type is not active")
        
        if not scholarship.is_application_period:
            raise ValidationError("Application period has ended")
        
        # Check student type eligibility  
        eligible_types: List[str] = scholarship.eligible_student_types or []
        student_type = self.student_service.get_student_type_from_data(student_data)
        if eligible_types and student_type not in eligible_types:
            raise ValidationError(f"Student type {student_type} is not eligible for this scholarship")
        
        # Check whitelist eligibility using user ID instead of student ID
        # Since students are now external, whitelist should use user IDs
        user_id = application_data.user_id if hasattr(application_data, 'user_id') else None
        if user_id and scholarship.whitelist_enabled:
            # Check if user is in whitelist (whitelist now contains user IDs)
            if not scholarship.is_user_in_whitelist(user_id):
                raise ValidationError("您不在此獎學金的白名單內，僅限預先核准的學生申請")
        
        # All validation requirements (ranking, term count, etc.) are now handled by scholarship rules
        # No hardcoded validation logic needed here
        
        # Check for existing active applications
        # In the new design, we need to get user ID differently
        # Get scholarship type ID for the query
        stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
        result = await self.db.execute(stmt)
        scholarship = result.scalar_one_or_none()
        
        if not scholarship:
            raise NotFoundError("Scholarship type", scholarship_type)
        
        # Check for existing applications (using user_id since student_id removed)
        stmt = select(Application).where(
            and_(
                Application.user_id == user_id,
                Application.scholarship_type_id == scholarship.id,
                Application.status.in_([
                    ApplicationStatus.SUBMITTED.value,
                    ApplicationStatus.UNDER_REVIEW.value,
                    ApplicationStatus.PENDING_RECOMMENDATION.value,
                    ApplicationStatus.RECOMMENDED.value
                ])
            )
        )
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            raise ConflictError("You already have an active application for this scholarship")
    
    async def create_application(
        self,
        user_id: int,
        student_code: str,  # User's nycu_id for fetching student data
        application_data: ApplicationCreate,
        is_draft: bool = False
    ) -> ApplicationResponse:
        """Create a new application (draft or submitted)"""
        logger.debug(f"Starting application creation for user_id={user_id}, student_code={student_code}, is_draft={is_draft}")
        logger.debug(f"Application data received: {application_data.dict(exclude_none=True)}")
        
        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one()
        
        # Get student data from external API
        logger.debug(f"Fetching student data for student_code={student_code}")
        student_snapshot = await self.student_service.get_student_snapshot(student_code)
        logger.debug(f"Student snapshot: {student_snapshot}")
        
        # Get scholarship type
        stmt = select(ScholarshipType).where(ScholarshipType.code == application_data.scholarship_type)
        result = await self.db.execute(stmt)
        scholarship = result.scalar_one()
        
        # Get the specific configuration that the student is eligible for
        from app.models.scholarship import ScholarshipConfiguration
        
        config_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.id == application_data.configuration_id
        )
        config_result = await self.db.execute(config_stmt)
        config = config_result.scalar_one_or_none()
        
        if not config:
            raise ValueError(f"Configuration with id {application_data.configuration_id} not found")
        
        # Verify the configuration belongs to the scholarship type
        if config.scholarship_type_id != scholarship.id:
            raise ValueError(f"Configuration {application_data.configuration_id} does not belong to scholarship type {application_data.scholarship_type}")
        
        # TODO: Add eligibility verification here
        # We should verify that the student is actually eligible for this specific configuration
        # by calling the eligibility service to check if this configuration appears in their eligible scholarships
        
        # Use configuration's academic year and semester
        academic_year = config.academic_year
        semester = config.semester  # This can be None for yearly scholarships
        logger.debug(f"Using config {config.id}: academic_year={academic_year}, semester={semester}")
        
        # Create application ID
        app_id = f"APP-{datetime.now().year}-{str(uuid.uuid4())[:8]}"
        
        # Serialize form data for JSON storage
        serialized_form_data = self._serialize_for_json(application_data.form_data.dict())
        
        # Determine status based on is_draft flag
        if is_draft:
            status = ApplicationStatus.DRAFT.value
            status_name = "草稿"
        else:
            status = ApplicationStatus.SUBMITTED.value
            status_name = "已提交"
        
        # Create application
        application = Application(
            app_id=app_id,
            user_id=user_id,
            # student_id removed - student data is now in student_data JSON field
            scholarship_type_id=scholarship.id,
            scholarship_configuration_id=config.id,  # Store the specific configuration
            scholarship_name=config.config_name,  # Use configuration name
            amount=config.amount,  # Use amount from configuration
            scholarship_subtype_list=application_data.scholarship_subtype_list,
            sub_type_selection_mode=scholarship.sub_type_selection_mode or "single",
            status=status,
            status_name=status_name,
            is_renewal=application_data.is_renewal or False,  # 設置續領申請標識
            academic_year=academic_year,
            semester=self._convert_semester_to_string(semester),  # Convert to string or None
            student_data=student_snapshot,
            submitted_form_data=serialized_form_data,
            agree_terms=application_data.agree_terms or False
        )
        
        # Set submission timestamp if not draft
        if not is_draft:
            application.submitted_at = datetime.now(timezone.utc)
        
        self.db.add(application)
        await self.db.commit()
        await self.db.refresh(application)
        
        # Clone fixed documents (like bank account proof) for both draft and submitted applications
        # This ensures that fixed documents are available for preview and progress calculation
        try:
            await self._clone_user_profile_documents(application, user)
        except Exception as e:
            # Don't fail the entire application creation if document cloning fails
            logger.warning(f"Failed to clone fixed documents for application {app_id}: {e}", exc_info=True)
        
        # Load relationships for response
        stmt = select(Application).where(Application.id == application.id).options(
            selectinload(Application.files),
            selectinload(Application.reviews),
            selectinload(Application.professor_reviews)
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one()
        
        logger.debug(f"Application created successfully: {app_id} with status: {status}")
        return await self._build_application_response(application, user)
    

    
    async def get_user_applications(
        self, 
        user: User, 
        status: Optional[str] = None
    ) -> List[ApplicationListResponse]:
        """Get applications for a user"""
        stmt = select(Application).options(
            selectinload(Application.files),
            selectinload(Application.scholarship)
        ).where(Application.user_id == user.id)
        
        if status:
            stmt = stmt.where(Application.status == status)
        
        stmt = stmt.order_by(desc(Application.created_at))
        result = await self.db.execute(stmt)
        applications = result.scalars().all()
        
        response_list = []
        for application in applications:
            # 整合文件資訊到 submitted_form_data.documents
            integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}
            
            if application.files:
                # 生成文件訪問 token
                from app.core.config import settings
                from app.core.security import create_access_token
                
                token_data = {"sub": str(user.id)}
                access_token = create_access_token(token_data)
                base_url = f"{settings.base_url}{settings.api_v1_str}"
                
                # 確保 documents 陣列存在
                if 'documents' not in integrated_form_data:
                    integrated_form_data['documents'] = []
                
                # 為每個 ApplicationFile 創建或更新對應的 document 記錄
                for file in application.files:
                    # 檢查是否已存在此文件的記錄
                    existing_doc = next((doc for doc in integrated_form_data['documents'] 
                                       if doc.get('document_type') == file.file_type or doc.get('document_id') == file.file_type), None)
                    
                    # 創建文件資訊
                    file_info = {
                        "document_id": file.file_type,
                        "document_type": file.file_type,
                        "document_name": self._get_document_display_name(file.file_type),
                        "file_id": file.id,
                        "filename": file.filename,
                        "original_filename": file.original_filename,
                        "file_size": file.file_size,
                        "mime_type": file.mime_type or file.content_type,
                        "file_path": f"{base_url}/files/applications/{application.id}/files/{file.id}?token={access_token}",
                        "download_url": f"{base_url}/files/applications/{application.id}/files/{file.id}/download?token={access_token}",
                        "is_verified": file.is_verified,
                        "object_name": file.object_name,
                        "upload_time": file.uploaded_at.isoformat() if file.uploaded_at else None
                    }
                    
                    if existing_doc:
                        # 更新現有記錄
                        existing_doc.update(file_info)
                    else:
                        # 新增記錄
                        integrated_form_data['documents'].append(file_info)
            
            # 創建響應數據
            app_data = ApplicationListResponse(
                id=application.id,
                app_id=application.app_id,
                user_id=application.user_id,
                student_id=user.nycu_id if user else None,
                scholarship_type=application.scholarship.code if application.scholarship else None,
                scholarship_type_id=application.scholarship_type_id,
                scholarship_subtype_list=application.scholarship_subtype_list or [],
                status=application.status,
                status_name=application.status_name,
                is_renewal=application.is_renewal,  # 添加續領申請標識
                academic_year=application.academic_year,
                semester=self._convert_semester_to_string(application.semester),
                student_data=application.student_data,
                submitted_form_data=integrated_form_data,  # 使用整合後的表單資料
                agree_terms=application.agree_terms,
                professor_id=application.professor_id,
                reviewer_id=application.reviewer_id,
                final_approver_id=application.final_approver_id,
                review_score=application.review_score,
                review_comments=application.review_comments,
                rejection_reason=application.rejection_reason,
                submitted_at=application.submitted_at,
                reviewed_at=application.reviewed_at,
                approved_at=application.approved_at,
                created_at=application.created_at,
                updated_at=application.updated_at,
                meta_data=application.meta_data
            )
            
            # Add Chinese scholarship type name
            app_data = self._add_scholarship_type_zh(app_data)
            response_list.append(app_data)
        
        return response_list
    
    async def get_student_dashboard_stats(self, user: User) -> Dict[str, Any]:
        """Get dashboard statistics for student"""
        # Count applications by status
        stmt = select(
            Application.status,
            func.count(Application.id).label('count')
        ).where(Application.user_id == user.id).group_by(Application.status)
        
        result = await self.db.execute(stmt)
        status_counts = {}
        total_applications = 0
        
        for row in result:
            count_value = row[1]  # Access by index since count is the second column
            status_counts[row[0]] = count_value  # status is the first column
            total_applications += count_value
        
        # Get recent applications with files loaded
        stmt = select(Application).options(
            selectinload(Application.files),
            selectinload(Application.scholarship)
        ).where(
            Application.user_id == user.id
        ).order_by(desc(Application.created_at)).limit(5)
        
        result = await self.db.execute(stmt)
        recent_applications = result.scalars().all()
        
        # Convert to response models with integrated file data
        recent_applications_response = []
        for application in recent_applications:
            # 整合文件資訊到 submitted_form_data.documents
            integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}
            
            if application.files:
                # 生成文件訪問 token
                from app.core.config import settings
                from app.core.security import create_access_token
                
                token_data = {"sub": str(user.id)}
                access_token = create_access_token(token_data)
                
                # 更新 submitted_form_data 中的 documents
                if 'documents' in integrated_form_data:
                    existing_docs = integrated_form_data['documents']
                    for existing_doc in existing_docs:
                        # 查找對應的文件記錄
                        matching_file = next((f for f in application.files if f.file_type == existing_doc.get('document_id')), None)
                        if matching_file:
                            # 更新現有文件資訊
                            base_url = f"{settings.base_url}{settings.api_v1_str}"
                            existing_doc.update({
                                "file_id": matching_file.id,
                                "filename": matching_file.filename,
                                "original_filename": matching_file.original_filename,
                                "file_size": matching_file.file_size,
                                "mime_type": matching_file.mime_type or matching_file.content_type,
                                "file_path": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}?token={access_token}",
                                "download_url": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}/download?token={access_token}",
                                "is_verified": matching_file.is_verified,
                                "object_name": matching_file.object_name
                            })
            
            # 創建響應數據
            app_data = ApplicationListResponse(
                id=application.id,
                app_id=application.app_id,
                user_id=application.user_id,
                student_id=user.nycu_id if user else None,
                scholarship_type=application.scholarship.code if application.scholarship else None,
                scholarship_type_id=application.scholarship_type_id,
                status=application.status,
                status_name=application.status_name,
                academic_year=application.academic_year,
                semester=self._convert_semester_to_string(application.semester),
                student_data=application.student_data,
                submitted_form_data=integrated_form_data,  # 使用整合後的表單資料
                agree_terms=application.agree_terms,
                professor_id=application.professor_id,
                reviewer_id=application.reviewer_id,
                final_approver_id=application.final_approver_id,
                review_score=application.review_score,
                review_comments=application.review_comments,
                rejection_reason=application.rejection_reason,
                submitted_at=application.submitted_at,
                reviewed_at=application.reviewed_at,
                approved_at=application.approved_at,
                created_at=application.created_at,
                updated_at=application.updated_at,
                meta_data=application.meta_data
            )
            
            # Add Chinese scholarship type name
            app_data = self._add_scholarship_type_zh(app_data)
            recent_applications_response.append(app_data)
        
        return {
            "total_applications": total_applications,
            "status_counts": status_counts,
            "recent_applications": recent_applications_response
        }
    
    async def get_application_by_id(self, application_id: int, current_user: User) -> Optional[Application]:
        """Get application by ID with proper access control"""
        stmt = select(Application).options(
            selectinload(Application.files),
            selectinload(Application.reviews),
            selectinload(Application.professor_reviews),
            selectinload(Application.scholarship)
        ).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        
        if not application:
            return None
            
        # Check access permissions
        if current_user.role == UserRole.STUDENT:
            if application.user_id != current_user.id:
                return None
        elif current_user.role == UserRole.PROFESSOR:
            # TODO: Add professor-student relationship check when implemented
            # For now, allow professors to access all applications
            pass
        elif current_user.role in [UserRole.COLLEGE, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            # College, Admin, and Super Admin can access any application
            pass
        else:
            return None

        # 整合文件資訊到 submitted_form_data.documents
        if application.submitted_form_data and application.files:
            integrated_form_data = application.submitted_form_data.copy()
            
            # 生成文件訪問 token
            from app.core.config import settings
            from app.core.security import create_access_token
            
            token_data = {"sub": str(current_user.id)}
            access_token = create_access_token(token_data)
            
            # 更新 submitted_form_data 中的 documents
            if 'documents' in integrated_form_data:
                existing_docs = integrated_form_data['documents']
                for existing_doc in existing_docs:
                    # 查找對應的文件記錄
                    matching_file = next((f for f in application.files if f.file_type == existing_doc.get('document_id')), None)
                    if matching_file:
                        # 更新現有文件資訊
                        base_url = f"{settings.base_url}{settings.api_v1_str}"
                        existing_doc.update({
                            "file_id": matching_file.id,
                            "filename": matching_file.filename,
                            "original_filename": matching_file.original_filename,
                            "file_size": matching_file.file_size,
                            "mime_type": matching_file.mime_type or matching_file.content_type,
                            "file_path": f"{base_url}/files/applications/{application_id}/files/{matching_file.id}?token={access_token}",
                            "download_url": f"{base_url}/files/applications/{application_id}/files/{matching_file.id}/download?token={access_token}",
                            "is_verified": matching_file.is_verified,
                            "object_name": matching_file.object_name
                        })
            
            # 更新 application 的 submitted_form_data
            application.submitted_form_data = integrated_form_data

        return application
    
    async def update_application(
        self,
        application_id: int,
        update_data: ApplicationUpdate,
        current_user: User
    ) -> Application:
        """更新申請資料"""
        
        # 取得申請
        application = await self.get_application_by_id(application_id, current_user)
        if not application:
            raise NotFoundError(f"Application {application_id} not found")
            
        # 檢查是否可以編輯
        if not application.is_editable:
            raise ValidationError("Application cannot be edited in current status")
        
        # Store old subtype list for comparison
        old_subtype_list = application.scholarship_subtype_list.copy() if application.scholarship_subtype_list else []
        
        # 更新表單資料
        if update_data.form_data:
            # Serialize form data to handle datetime objects properly
            application.submitted_form_data = self._serialize_for_json(update_data.form_data.dict())
            
        # 更新狀態
        if update_data.status:
            application.status = update_data.status
            
        # 更新續領申請標識
        if update_data.is_renewal is not None:
            application.is_renewal = update_data.is_renewal
            
        # 更新子項目列表（如果提供）
        if update_data.scholarship_subtype_list is not None:
            application.scholarship_subtype_list = update_data.scholarship_subtype_list
            
        await self.db.commit()
        await self.db.refresh(application)
        
        # Clone bank account proof document when saving draft or updating application
        # This ensures the document is available in the application
        logger.info(f"Cloning bank account proof document for application {application.app_id}")
        try:
            await self._clone_user_profile_documents(application, current_user)
        except Exception as e:
            logger.warning(f"Failed to clone bank account proof document for application {application.app_id}: {e}")
            import traceback
            traceback.print_exc()
        
        # Check if subtype list changed and re-clone fixed documents if necessary
        new_subtype_list = application.scholarship_subtype_list.copy() if application.scholarship_subtype_list else []
        if old_subtype_list != new_subtype_list:
            logger.info(f"Subtype list changed from {old_subtype_list} to {new_subtype_list}, re-cloning fixed documents")
            try:
                await self._clone_user_profile_documents(application, current_user)
            except Exception as e:
                logger.warning(f"Failed to re-clone fixed documents after subtype change for application {application.app_id}: {e}")
        
        return application
    
    async def update_student_data(
        self,
        application_id: int,
        student_data_update: StudentDataSchema,
        current_user: User,
        refresh_from_api: bool = False
    ) -> Application:
        """更新申請中的學生資料
        
        Args:
            application_id: 申請ID
            student_data_update: 要更新的學生資料
            current_user: 當前用戶
            refresh_from_api: 是否重新從外部API獲取基本學生資料
        """
        
        # 取得申請
        application = await self.get_application_by_id(application_id, current_user)
        if not application:
            raise NotFoundError(f"Application {application_id} not found")
        
        # 檢查權限
        if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.COLLEGE]:
            if application.user_id != current_user.id:
                raise AuthorizationError("You can only update your own application data")
        
        # 檢查是否可以編輯
        if application.status not in [ApplicationStatus.DRAFT.value, ApplicationStatus.RETURNED.value]:
            raise ValidationError("Cannot update student data for submitted applications")
        
        # 獲取當前學生資料
        current_student_data = application.student_data or {}
        
        # 如果需要，重新從外部API獲取基本學生資料
        if refresh_from_api and current_user.nycu_id:
            fresh_api_data = await self.student_service.get_student_snapshot(current_user.nycu_id)
            if fresh_api_data:
                # 合併API資料，但保留用戶輸入的資料
                current_student_data.update(fresh_api_data)
        
        # 合併用戶更新的資料
        update_dict = student_data_update.model_dump(exclude_none=True)
        for field, value in update_dict.items():
            if field in ['financial_info', 'supervisor_info']:
                # 對於嵌套對象，進行深度合併
                if value:
                    if field not in current_student_data:
                        current_student_data[field] = {}
                    current_student_data[field].update(value)
            else:
                # 對於普通欄位，直接更新
                current_student_data[field] = value
        
        # 更新到資料庫
        application.student_data = current_student_data
        
        await self.db.commit()
        await self.db.refresh(application)
        
        return application
    
    async def submit_application(
        self,
        application_id: int,
        user: User
    ) -> ApplicationResponse:
        """提交申請"""
        # Get application with relationships loaded
        stmt = select(Application).options(
            selectinload(Application.files),
            selectinload(Application.reviews),
            selectinload(Application.professor_reviews),
            selectinload(Application.scholarship)
        ).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        
        if not application:
            raise NotFoundError(f"Application {application_id} not found")
            
        if not application.is_editable:
            raise ValidationError("Application cannot be submitted in current status")
            
        # 驗證所有必填欄位
        form_data = ApplicationFormData(**application.submitted_form_data)
        
        # 處理銀行帳戶證明文件 clone（從個人資料複製到申請）
        await self._clone_user_profile_documents(application, user)
        
        # 更新狀態為已提交
        application.status = ApplicationStatus.SUBMITTED.value
        application.status_name = "已提交"
        application.submitted_at = datetime.now(timezone.utc)
        application.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(application, ['files', 'reviews', 'professor_reviews', 'scholarship'])
        
        # 發送通知
        try:
            await self.emailService.send_submission_notification(application, db=self.db)
        except Exception as e:
            logger.error(f"Failed to send submission notification email: {e}")
        
        # 整合文件資訊到 submitted_form_data.documents
        integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}
        
        # 生成文件訪問 token
        from app.core.config import settings
        from app.core.security import create_access_token
        
        token_data = {"sub": str(user.id)}
        access_token = create_access_token(token_data)
        
        # 將 files 的完整資訊合併到 documents 中
        if application.files:
            integrated_documents = []
            for file in application.files:
                # 生成文件 URL
                base_url = f"{settings.base_url}{settings.api_v1_str}"
                file_path = f"{base_url}/files/applications/{application_id}/files/{file.id}?token={access_token}"
                download_url = f"{base_url}/files/applications/{application_id}/files/{file.id}/download?token={access_token}"
                
                # 整合文件資訊
                integrated_document = {
                    "document_id": file.file_type,
                    "document_type": file.file_type,
                    "file_id": file.id,
                    "filename": file.filename,
                    "original_filename": file.original_filename,
                    "file_size": file.file_size,
                    "mime_type": file.mime_type or file.content_type,
                    "file_path": file_path,
                    "download_url": download_url,
                    "upload_time": file.uploaded_at.isoformat() if file.uploaded_at else None,
                    "is_verified": file.is_verified,
                    "object_name": file.object_name
                }
                integrated_documents.append(integrated_document)
            
            # 更新 submitted_form_data 中的 documents
            if 'documents' in integrated_form_data:
                # 如果已有 documents，合併文件資訊
                existing_docs = integrated_form_data['documents']
                for existing_doc in existing_docs:
                    # 查找對應的文件記錄
                    matching_file = next((f for f in application.files if f.file_type == existing_doc.get('document_id')), None)
                    if matching_file:
                        # 更新現有文件資訊
                        base_url = f"{settings.base_url}{settings.api_v1_str}"
                        existing_doc.update({
                            "file_id": matching_file.id,
                            "filename": matching_file.filename,
                            "original_filename": matching_file.original_filename,
                            "file_size": matching_file.file_size,
                            "mime_type": matching_file.mime_type or matching_file.content_type,
                            "file_path": f"{base_url}/files/applications/{application_id}/files/{matching_file.id}?token={access_token}",
                            "download_url": f"{base_url}/files/applications/{application_id}/files/{matching_file.id}/download?token={access_token}",
                            "is_verified": matching_file.is_verified,
                            "object_name": matching_file.object_name
                        })
            else:
                # 如果沒有 documents，創建新的
                integrated_form_data['documents'] = integrated_documents
        
        # Convert application to response model
        response_data = {
            'id': application.id,
            'app_id': application.app_id,
            'user_id': application.user_id,
            'student_id': self._get_student_id_from_user(user),
            'scholarship_type_id': application.scholarship_type_id,
            'scholarship_subtype_list': application.scholarship_subtype_list,
            'status': application.status,
            'status_name': application.status_name,
            'academic_year': application.academic_year,
            'semester': application.semester,
            'student_data': application.student_data,
            'submitted_form_data': integrated_form_data,  # 使用整合後的表單資料
            'agree_terms': application.agree_terms,
            'professor_id': application.professor_id,
            'reviewer_id': application.reviewer_id,
            'final_approver_id': application.final_approver_id,
            'review_score': application.review_score,
            'review_comments': application.review_comments,
            'rejection_reason': application.rejection_reason,
            'submitted_at': application.submitted_at,
            'reviewed_at': application.reviewed_at,
            'approved_at': application.approved_at,
            'created_at': application.created_at,
            'updated_at': application.updated_at,
            'meta_data': application.meta_data,
            # 移除獨立的 files 欄位
            'reviews': [
                {
                    'id': review.id,
                    'reviewer_id': review.reviewer_id,
                    'reviewer_name': review.reviewer_name,
                    'score': review.score,
                    'comments': review.comments,
                    'reviewed_at': review.reviewed_at
                } for review in application.reviews
            ],
            'professor_reviews': [
                {
                    'id': review.id,
                    'professor_id': review.professor_id,
                    'professor_name': review.professor_name,
                    'score': review.score,
                    'comments': review.comments,
                    'reviewed_at': review.reviewed_at
                } for review in application.professor_reviews
            ]
        }
        
        return ApplicationResponse(**response_data)
    
    async def get_applications_for_review(
        self, 
        current_user: User,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        scholarship_type: Optional[str] = None
    ) -> List[ApplicationListResponse]:
        """Get applications for review with proper access control"""
        # Build query based on user role
        query = select(Application).options(
            selectinload(Application.files),
            selectinload(Application.scholarship),
            selectinload(Application.user)  # Eagerly load user to avoid N+1 queries
        )
        
        if current_user.role == UserRole.PROFESSOR:
            # TODO: Add professor-student relationship filter when implemented
            # For now, professors can see all applications
            pass
        elif current_user.role in [UserRole.COLLEGE, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            # College, Admin, and Super Admin can see all applications
            pass
        else:
            # Other roles cannot review applications
            return []
        
        # Apply filters
        if status:
            query = query.where(Application.status == status)
        if scholarship_type:
            # Get scholarship type ID for filtering
            stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
            result = await self.db.execute(stmt)
            scholarship = result.scalar_one_or_none()
            if scholarship:
                query = query.where(Application.scholarship_type_id == scholarship.id)
        
        # Apply pagination
        query = query.offset(skip).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        applications = result.scalars().all()
        
        # Convert to response models
        response_applications = []
        for application in applications:
            # 整合文件資訊到 submitted_form_data.documents
            integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}
            
            if application.files:
                # 生成文件訪問 token
                from app.core.config import settings
                from app.core.security import create_access_token
                
                token_data = {"sub": str(current_user.id)}
                access_token = create_access_token(token_data)
                
                # 更新 submitted_form_data 中的 documents
                if 'documents' in integrated_form_data:
                    existing_docs = integrated_form_data['documents']
                    for existing_doc in existing_docs:
                        # 查找對應的文件記錄
                        matching_file = next((f for f in application.files if f.file_type == existing_doc.get('document_id')), None)
                        if matching_file:
                            # 更新現有文件資訊
                            base_url = f"{settings.base_url}{settings.api_v1_str}"
                            existing_doc.update({
                                "file_id": matching_file.id,
                                "filename": matching_file.filename,
                                "original_filename": matching_file.original_filename,
                                "file_size": matching_file.file_size,
                                "mime_type": matching_file.mime_type or matching_file.content_type,
                                "file_path": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}?token={access_token}",
                                "download_url": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}/download?token={access_token}",
                                "is_verified": matching_file.is_verified,
                                "object_name": matching_file.object_name
                            })
            
            # Use eagerly loaded user (already loaded with selectinload)
            app_user = application.user
            
            # 創建響應數據
            app_data = ApplicationListResponse(
                id=application.id,
                app_id=application.app_id,
                user_id=application.user_id,
                student_id=app_user.nycu_id if app_user else None,
                scholarship_type=application.scholarship.code if application.scholarship else None,
                scholarship_type_id=application.scholarship_type_id,
                status=application.status,
                status_name=application.status_name,
                academic_year=application.academic_year,
                semester=self._convert_semester_to_string(application.semester),
                student_data=application.student_data,
                submitted_form_data=integrated_form_data,  # 使用整合後的表單資料
                agree_terms=application.agree_terms,
                professor_id=application.professor_id,
                reviewer_id=application.reviewer_id,
                final_approver_id=application.final_approver_id,
                review_score=application.review_score,
                review_comments=application.review_comments,
                rejection_reason=application.rejection_reason,
                submitted_at=application.submitted_at,
                reviewed_at=application.reviewed_at,
                approved_at=application.approved_at,
                created_at=application.created_at,
                updated_at=application.updated_at,
                meta_data=application.meta_data
            )
            
            # Add Chinese scholarship type name
            app_data = self._add_scholarship_type_zh(app_data)
            response_applications.append(app_data)
        
        return response_applications
    
    async def update_application_status(
        self, 
        application_id: int, 
        user: User, 
        status_update: ApplicationStatusUpdate
    ) -> ApplicationResponse:
        """Update application status (staff only)"""
        if not (user.has_role(UserRole.ADMIN) or user.has_role(UserRole.COLLEGE) or user.has_role(UserRole.PROFESSOR) or user.has_role(UserRole.SUPER_ADMIN)):
            raise AuthorizationError("Staff access required")
        
        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        
        if not application:
            raise NotFoundError("Application", str(application_id))
        
        # Update status
        application.status = status_update.status
        application.reviewer_id = user.id
        
        if status_update.status == ApplicationStatus.APPROVED.value:
            application.approved_at = datetime.utcnow()
            application.status_name = "已核准"
        elif status_update.status == ApplicationStatus.REJECTED.value:
            application.status_name = "已拒絕"
            if hasattr(status_update, 'rejection_reason') and status_update.rejection_reason:
                application.rejection_reason = status_update.rejection_reason
        
        if hasattr(status_update, 'comments') and status_update.comments:
            application.review_comments = status_update.comments
        
        application.reviewed_at = datetime.utcnow()
        
        await self.db.commit()
        
        # Return fresh copy with all relationships loaded
        return await self.get_application_by_id(application_id, user)
    
    async def upload_application_file(
        self, 
        application_id: int, 
        user: User, 
        file, 
        file_type: str
    ) -> Dict[str, Any]:
        """Upload file for application"""
        # Get application
        stmt = select(Application).where(
            and_(Application.id == application_id, Application.user_id == user.id)
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        
        if not application:
            raise NotFoundError("Application", str(application_id))
        
        if not application.is_editable:
            raise BusinessLogicError("Cannot upload files to application in current status")
        
        # For now, return a placeholder response
        # In a real implementation, this would handle file storage
        return {
            "message": "File upload functionality not yet implemented",
            "application_id": application_id,
            "file_type": file_type,
            "filename": getattr(file, 'filename', 'unknown')
        }
    
    async def submit_professor_review(self, application_id: int, user: User, review_data) -> ApplicationResponse:
        """Submit professor review for an application"""
        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        if not application:
            raise NotFoundError("Application", str(application_id))
        # Only the assigned professor can submit
        if application.professor_id != user.id:
            raise AuthorizationError("You are not the assigned professor for this application")
        
        # Create professor review record
        from app.models.application import ProfessorReview, ProfessorReviewItem
        
        review = ProfessorReview(
            application_id=application_id,
            professor_id=user.id,
            recommendation=review_data.recommendation,
            review_status=review_data.review_status or "completed",
            reviewed_at=datetime.utcnow()
        )
        self.db.add(review)
        await self.db.flush()  # Get the review ID
        
        # Create review items for each sub-type
        for item_data in review_data.items:
            review_item = ProfessorReviewItem(
                review_id=review.id,
                sub_type_code=item_data.sub_type_code,
                is_recommended=item_data.is_recommended,
                comments=item_data.comments
            )
            self.db.add(review_item)
        
        await self.db.commit()
        
        # Return fresh copy with all relationships loaded
        return await self.get_application_by_id(application_id)
    
    async def create_professor_review(self, application_id: int, user: User, review_data) -> ApplicationResponse:
        """Create a professor review record and notify college reviewers"""
        from app.models.application import ProfessorReview, ProfessorReviewItem
        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        if not application:
            raise NotFoundError("Application", str(application_id))
        # Only the assigned professor can submit
        if application.professor_id != user.id:
            raise AuthorizationError("You are not the assigned professor for this application")
        
        # Create review record
        review = ProfessorReview(
            application_id=application_id,
            professor_id=user.id,
            recommendation=review_data.recommendation,
            review_status=review_data.review_status or "completed",
            reviewed_at=datetime.utcnow()
        )
        self.db.add(review)
        await self.db.flush()  # Get the review ID
        
        # Create review items for each sub-type
        for item_data in review_data.items:
            review_item = ProfessorReviewItem(
                review_id=review.id,
                sub_type_code=item_data.sub_type_code,
                is_recommended=item_data.is_recommended,
                comments=item_data.comments
            )
            self.db.add(review_item)
        
        await self.db.commit()
        
        # 自動寄信通知學院審查人員
        try:
            await self.emailService.send_to_college_reviewers(application, db=self.db)
        except Exception as e:
            logger.error(f"Failed to send college reviewer notification email: {e}")
        
        # Return fresh copy with all relationships loaded
        return await self.get_application_by_id(application_id)
    
    async def upload_application_file_minio(
        self, 
        application_id: int, 
        user: User, 
        file, 
        file_type: str
    ) -> Dict[str, Any]:
        """Upload application file using MinIO"""
        # Verify application exists and user has access
        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        
        if not application:
            raise NotFoundError("Application", str(application_id))
        
        # Check upload permissions based on role
        if user.role == UserRole.STUDENT:
            # Students can only upload to their own applications
            if application.user_id != user.id:
                raise AuthorizationError("Cannot upload files to other students' applications")
        elif user.role == UserRole.PROFESSOR:
            # Professors can upload files to their students' applications
            # TODO: Add professor-student relationship check when implemented
            # For now, allow professors to upload to any application
            pass
        elif user.role in [UserRole.COLLEGE, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            # College, Admin, and Super Admin can upload to any application
            pass
        else:
            # Other roles are not allowed to upload
            raise AuthorizationError("Upload access denied")
        
        # Upload file to MinIO
        object_name, file_size = await minio_service.upload_file(file, application_id, file_type)
        
        # Import ApplicationFile here to avoid circular imports
        from app.models.application import ApplicationFile
        
        # Save file metadata to database
        file_record = ApplicationFile(
            application_id=application_id,
            filename=file.filename,  # Keep original filename for display
            original_filename=file.filename,  # Store original filename
            file_type=file_type,
            file_size=file_size,
            object_name=object_name,  # This is now UUID-based path
            uploaded_at=datetime.utcnow(),
            content_type=file.content_type or 'application/octet-stream',
            mime_type=file.content_type or 'application/octet-stream'
        )
        
        self.db.add(file_record)
        await self.db.commit()
        await self.db.refresh(file_record)
        
        return {
            "success": True,
            "message": "File uploaded successfully",
            "data": {
                "file_id": file_record.id,
                "filename": file_record.filename,
                "file_type": file_record.file_type,
                "file_size": file_record.file_size,
                "uploaded_at": file_record.uploaded_at.isoformat()
            }
        }
    
    def _add_scholarship_type_zh(self, app_data: ApplicationListResponse) -> ApplicationListResponse:
        """Add Chinese scholarship type name to application response"""
        scholarship_type_zh = {
            "undergraduate_freshman": "學士班新生獎學金",
            "phd_nstc": "國科會博士生獎學金", 
            "phd_moe": "教育部博士生獎學金",
            "direct_phd": "逕博獎學金"
        }
        app_data.scholarship_type_zh = scholarship_type_zh.get(app_data.scholarship_type, app_data.scholarship_type)
        return app_data
    
    async def search_applications(
        self,
        search_criteria: Dict[str, Any]
    ) -> List[Application]:
        """搜尋申請"""
        query = select(Application)
        
        # 動態添加搜尋條件
        for field, value in search_criteria.items():
            if field.startswith('student.'):
                # 搜尋學生資料
                json_path = field.replace('student.', '')
                query = query.filter(
                    Application.student_data[json_path].astext == str(value)
                )
            elif field.startswith('form.'):
                # 搜尋表單資料
                json_path = field.replace('form.', '')
                query = query.filter(
                    Application.submitted_form_data[json_path].astext == str(value)
                )
            else:
                # 一般欄位搜尋
                query = query.filter(getattr(Application, field) == value)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_applications(
        self, 
        current_user: User,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        scholarship_type: Optional[str] = None
    ) -> List[ApplicationListResponse]:
        """Get applications with proper access control"""
        # Build query based on user role
        query = select(Application).options(
            selectinload(Application.files),
            selectinload(Application.scholarship),
            selectinload(Application.user)  # Eagerly load user to avoid N+1 queries
        )
        
        if current_user.role == UserRole.STUDENT:
            # Students can only see their own applications
            query = query.where(Application.user_id == current_user.id)
        elif current_user.role == UserRole.PROFESSOR:
            # TODO: Add professor-student relationship filter when implemented
            # For now, professors can see all applications
            pass
        elif current_user.role in [UserRole.COLLEGE, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            # College, Admin, and Super Admin can see all applications
            pass
        else:
            # Other roles cannot see any applications
            return []
        
        # Apply filters
        if status:
            query = query.where(Application.status == status)
        if scholarship_type:
            query = query.where(Application.scholarship_type == scholarship_type)
        
        # Apply pagination
        query = query.offset(skip).limit(limit)
        
        # Execute query
        result = await self.db.execute(query)
        applications = result.scalars().all()
        
        # Convert to response models
        response_applications = []
        for application in applications:
            # 整合文件資訊到 submitted_form_data.documents
            integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}
            
            if application.files:
                # 生成文件訪問 token
                from app.core.config import settings
                from app.core.security import create_access_token
                
                token_data = {"sub": str(current_user.id)}
                access_token = create_access_token(token_data)
                
                # 更新 submitted_form_data 中的 documents
                if 'documents' in integrated_form_data:
                    existing_docs = integrated_form_data['documents']
                    for existing_doc in existing_docs:
                        # 查找對應的文件記錄
                        matching_file = next((f for f in application.files if f.file_type == existing_doc.get('document_id')), None)
                        if matching_file:
                            # 更新現有文件資訊
                            base_url = f"{settings.base_url}{settings.api_v1_str}"
                            existing_doc.update({
                                "file_id": matching_file.id,
                                "filename": matching_file.filename,
                                "original_filename": matching_file.original_filename,
                                "file_size": matching_file.file_size,
                                "mime_type": matching_file.mime_type or matching_file.content_type,
                                "file_path": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}?token={access_token}",
                                "download_url": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}/download?token={access_token}",
                                "is_verified": matching_file.is_verified,
                                "object_name": matching_file.object_name
                            })
            
            # Use eagerly loaded user (already loaded with selectinload)
            app_user = application.user
            
            # 創建響應數據
            app_data = ApplicationListResponse(
                id=application.id,
                app_id=application.app_id,
                user_id=application.user_id,
                student_id=app_user.nycu_id if app_user else None,
                scholarship_type=application.scholarship.code if application.scholarship else None,
                scholarship_type_id=application.scholarship_type_id,
                status=application.status,
                status_name=application.status_name,
                academic_year=application.academic_year,
                semester=self._convert_semester_to_string(application.semester),
                student_data=application.student_data,
                submitted_form_data=integrated_form_data,  # 使用整合後的表單資料
                agree_terms=application.agree_terms,
                professor_id=application.professor_id,
                reviewer_id=application.reviewer_id,
                final_approver_id=application.final_approver_id,
                review_score=application.review_score,
                review_comments=application.review_comments,
                rejection_reason=application.rejection_reason,
                submitted_at=application.submitted_at,
                reviewed_at=application.reviewed_at,
                approved_at=application.approved_at,
                created_at=application.created_at,
                updated_at=application.updated_at,
                meta_data=application.meta_data
            )
            
            # Add Chinese scholarship type name
            app_data = self._add_scholarship_type_zh(app_data)
            response_applications.append(app_data)
        
        return response_applications
    
    async def delete_application(
        self,
        application_id: int,
        current_user: User
    ) -> bool:
        """Delete an application (only draft applications can be deleted)"""
        # Get application
        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        
        if not application:
            raise NotFoundError("Application", application_id)
        
        # Check if user has permission to delete this application
        if current_user.role == UserRole.STUDENT:
            if application.user_id != current_user.id:
                raise AuthorizationError("You can only delete your own applications")
        elif current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise AuthorizationError("You don't have permission to delete applications")
        
        # Only draft applications can be deleted
        if application.status != ApplicationStatus.DRAFT.value:
            raise ValidationError("Only draft applications can be deleted")
        
        # Delete associated files from MinIO if they exist
        if application.submitted_form_data and 'documents' in application.submitted_form_data:
            for doc in application.submitted_form_data['documents']:
                if 'file_path' in doc and doc['file_path']:
                    try:
                        # Extract object name from file path
                        # Assuming file_path format: applications/{application_id}/{file_type}/{filename}
                        object_name = doc['file_path']
                        if object_name.startswith('applications/'):
                            minio_service.delete_file(object_name)
                    except Exception as e:
                        # Log error but continue with deletion
                        logger.error(f"Error deleting file {doc['file_path']}: {e}")
        
        # Delete the application
        await self.db.delete(application)
        await self.db.commit()
        
        return True
    
    async def _clone_user_profile_documents(self, application: Application, user: User):
        """
        Clone all fixed documents from user profile to application-specific paths
        在申請提交或儲存草稿時，將個人資料中的固定文件複製到申請專屬路徑
        支援：銀行文件、其他固定文件
        """
        from app.services.user_profile_service import UserProfileService
        from app.models.application import ApplicationFile
        from sqlalchemy import select
        
        user_profile_service = UserProfileService(self.db)
        cloned_documents = []
        
        try:
            # 獲取用戶的個人資料
            user_profile = await user_profile_service.get_user_profile(user.id)
            
            if not user_profile:
                logger.debug(f"No user profile found for user {user.id}")
                return
            
            # 定義要複製的固定文件類型
            fixed_documents = [
                {
                    'file_type': 'bank_account_proof',
                    'profile_field': 'bank_document_photo_url',
                    'object_name_field': 'bank_document_object_name',
                    'document_name': '存摺封面'
                }
                # 未來可以新增更多固定文件類型，例如：
                # {
                #     'file_type': 'id_card',
                #     'profile_field': 'id_card_photo_url',
                #     'object_name_field': 'id_card_object_name',
                #     'document_name': '身份證件'
                # }
            ]
            
            for doc_config in fixed_documents:
                # 獲取文件 URL
                doc_url = getattr(user_profile, doc_config['profile_field'], None)
                if not doc_url:
                    logger.debug(f"No {doc_config['file_type']} found for user {user.id}")
                    continue
                
                # Check if the document is already cloned to avoid duplication
                existing_file_stmt = select(ApplicationFile).where(
                    ApplicationFile.application_id == application.id,
                    ApplicationFile.file_type == doc_config['file_type']
                )
                existing_file_result = await self.db.execute(existing_file_stmt)
                existing_file = existing_file_result.scalar_one_or_none()
                
                if existing_file:
                    logger.debug(f"{doc_config['document_name']} already cloned for application {application.app_id}, skipping")
                    continue
                
                logger.info(f"Cloning {doc_config['document_name']} for application {application.app_id}")
                
                # 使用儲存的 object_name，如果沒有則從 URL 提取
                if hasattr(user_profile, doc_config['object_name_field']):
                    source_object_name = getattr(user_profile, doc_config['object_name_field'], None)
                    if source_object_name:
                        filename = source_object_name.split('/')[-1]
                        file_extension = filename.split('.')[-1] if '.' in filename else 'jpg'
                    else:
                        # 從 URL 提取
                        filename = doc_url.split('/')[-1].split('?')[0]
                        file_extension = filename.split('.')[-1] if '.' in filename else 'jpg'
                        source_object_name = f"user-profiles/{user.id}/bank-documents/{filename}"
                else:
                    # 從 URL 提取（舊的邏輯作為備用）
                    filename = doc_url.split('/')[-1].split('?')[0]
                    file_extension = filename.split('.')[-1] if '.' in filename else 'jpg'
                    source_object_name = f"user-profiles/{user.id}/bank-documents/{filename}"
            
                
                # 使用 MinIO 服務複製文件到申請路徑
                new_object_name = minio_service.clone_file_to_application(
                    source_object_name=source_object_name,
                    application_id=application.app_id,
                    file_type=doc_config['file_type']
                )
                
                logger.debug(f"File cloned from {source_object_name} to {new_object_name}")
                
                # 創建 ApplicationFile 記錄 - 與動態上傳文件相同處理
                application_file = ApplicationFile(
                    application_id=application.id,
                    file_type=doc_config['file_type'],
                    filename=filename,
                    original_filename=filename,
                    file_size=0,  # 大小會在實際使用時獲取
                    content_type="application/octet-stream",  # 會在實際使用時更新
                    object_name=new_object_name,
                    is_verified=True,  # 固定文件預設已驗證
                    uploaded_at=datetime.now(timezone.utc)
                )
                
                self.db.add(application_file)
                await self.db.flush()  # 確保獲得 application_file.id
                
                cloned_documents.append({
                    'file_type': doc_config['file_type'],
                    'document_name': doc_config['document_name'],
                    'file_id': application_file.id,
                    'object_name': new_object_name
                })
            
            # 批量更新申請的 form_data
            if cloned_documents:
                form_data = application.submitted_form_data or {}
                
                # 生成文件訪問 URL
                from app.core.config import settings
                from app.core.security import create_access_token
                
                token_data = {"sub": str(user.id)}
                access_token = create_access_token(token_data)
                base_url = f"{settings.base_url}{settings.api_v1_str}"
                
                # 確保 documents 欄位存在
                if 'documents' not in form_data:
                    form_data['documents'] = []
                
                # 更新或新增複製的文件資訊
                for cloned_doc in cloned_documents:
                    doc_info = {
                        "document_id": cloned_doc['file_type'],
                        "document_type": cloned_doc['file_type'],
                        "document_name": cloned_doc['document_name'],
                        "file_id": cloned_doc['file_id'],
                        "filename": cloned_doc['object_name'].split('/')[-1],
                        "original_filename": cloned_doc['object_name'].split('/')[-1],
                        "file_path": f"{base_url}/files/applications/{application.id}/files/{cloned_doc['file_id']}?token={access_token}",
                        "download_url": f"{base_url}/files/applications/{application.id}/files/{cloned_doc['file_id']}/download?token={access_token}",
                        "object_name": cloned_doc['object_name'],
                        "is_verified": True,
                        "upload_time": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # 檢查是否已存在，如果存在則更新，否則新增
                    doc_found = False
                    for i, doc in enumerate(form_data['documents']):
                        if doc.get('document_type') == cloned_doc['file_type']:
                            form_data['documents'][i] = doc_info
                            doc_found = True
                            break
                    
                    if not doc_found:
                        form_data['documents'].append(doc_info)
                
                # 更新申請的 form_data
                application.submitted_form_data = form_data
                
                # 提交資料庫變更
                await self.db.commit()
                await self.db.refresh(application)
                
                logger.info(f"{len(cloned_documents)} documents successfully cloned and linked to application {application.app_id}")
            
        except Exception as e:
            logger.error(f"Failed to clone user profile documents for application {application.app_id}: {e}")
            # 不拋出異常，避免影響申請提交流程
            import traceback
            traceback.print_exc()
    
    def _get_document_display_name(self, file_type: str) -> str:
        """
        獲取文件類型的顯示名稱
        
        Args:
            file_type: 文件類型代碼
            
        Returns:
            文件顯示名稱
        """
        document_type_names = {
            'bank_account_proof': '存摺封面',
            'transcript': '成績單',
            'certificate': '證書',
            'recommendation_letter': '推薦信',
            'personal_statement': '個人陳述',
            'financial_statement': '財力證明',
            'other': '其他文件'
        }
        
        return document_type_names.get(file_type, file_type)