"""
Comprehensive scholarship service for scholarship management
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc, asc
from datetime import datetime, timezone, timedelta
import logging
from decimal import Decimal
from app.models.scholarship import ScholarshipType, ScholarshipStatus
from app.models.student import Student
from app.core.exceptions import ValidationError
from app.core.config import settings, DEV_SCHOLARSHIP_SETTINGS
from typing import List, Union, Optional, Dict, Any, Tuple

# Import comprehensive scholarship system models
from app.models.application import (
    Application, ApplicationFile, ApplicationReview, ProfessorReview,
    ApplicationStatus, ReviewStatus, ScholarshipMainType, ScholarshipSubType
)

logger = logging.getLogger(__name__)

class ScholarshipService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _safe_gpa_to_decimal(self, gpa: Union[str, int, float, Decimal]) -> Decimal:
        """Safely convert GPA to Decimal for comparison"""
        try:
            if isinstance(gpa, str):
                return Decimal(gpa)
            elif isinstance(gpa, (int, float)):
                return Decimal(str(gpa))
            elif isinstance(gpa, Decimal):
                return gpa
            else:
                logger.warning(f"Unexpected GPA type: {type(gpa)}, value: {gpa}")
                return Decimal("0.0")
        except Exception as e:
            logger.error(f"Error converting GPA '{gpa}' to Decimal: {e}")
            return Decimal("0.0")
    
    def _is_dev_mode(self) -> bool:
        """Check if running in development mode"""
        return settings.debug or settings.environment == "development"
    
    def _should_bypass_application_period(self) -> bool:
        """Check if should bypass application period in dev mode"""
        return (self._is_dev_mode() and 
                DEV_SCHOLARSHIP_SETTINGS.get("ALWAYS_OPEN_APPLICATION", False))
    
    def _should_bypass_whitelist(self) -> bool:
        """Check if should bypass whitelist in dev mode"""
        return (self._is_dev_mode() and 
                DEV_SCHOLARSHIP_SETTINGS.get("BYPASS_WHITELIST", False))
    
    async def get_eligible_scholarships(self, student: Student) -> List[ScholarshipType]:
        """Get scholarships that the student is eligible for"""
        # Get all active scholarships
        stmt = select(ScholarshipType).where(
            ScholarshipType.status == ScholarshipStatus.ACTIVE.value
        )
        result = await self.db.execute(stmt)
        scholarships = result.scalars().all()
        
        logger.info(f"Found {len(scholarships)} active scholarships")
        
        # Get student type from the student model
        from app.models.student import StudentType
        student_type = student.get_student_type()
        
        # Use student's term count (if available) or default to reasonable value
        completed_terms = student.std_termcount or 1
        
        # For now, we'll need to get GPA from external API or use default
        # This would be replaced with actual API call in production
        student_gpa = Decimal("3.0")  # Default GPA - should be fetched from student API
        
        logger.info(f"Student {student.std_stdcode} has {completed_terms} completed terms")
        logger.info(f"Student type: {student_type.value}")
        logger.info(f"Student GPA: {student_gpa}")
        
        eligible_scholarships = []
        for scholarship in scholarships:
            try:
                logger.info(f"\nChecking eligibility for scholarship: {scholarship.name}")
                logger.info(f"Application period: {scholarship.application_start_date} to {scholarship.application_end_date}")
                logger.info(f"Current time: {datetime.now(timezone.utc)}")
                logger.info(f"Scholarship category: {scholarship.category}")
                
                # Check if scholarship is in application period
                current_time = datetime.now(timezone.utc)
                in_application_period = True
                if scholarship.application_start_date and scholarship.application_end_date:
                    in_application_period = scholarship.application_start_date <= current_time <= scholarship.application_end_date
                
                if not self._should_bypass_application_period() and not in_application_period:
                    logger.info(f"Skipping {scholarship.name}: Not in application period")
                    continue
                elif self._should_bypass_application_period():
                    logger.info(f"DEV MODE: Bypassing application period check for {scholarship.name}")
                    
                # Check student type eligibility based on category
                # Map scholarship categories to student types that can apply
                eligible_for_category = True  # Default to eligible
                
                if scholarship.category == 'undergraduate_freshman':
                    # Only undergraduate students can apply for undergraduate scholarships
                    if student_type.value.lower() not in ['undergraduate', 'undergraduate_freshman']:
                        eligible_for_category = False
                elif scholarship.category == 'phd':
                    # PhD and graduate students can apply for PhD scholarships
                    if student_type.value.lower() not in ['phd', 'graduate', 'master']:
                        eligible_for_category = False
                elif scholarship.category == 'direct_phd':
                    # Only direct PhD students can apply
                    if student_type.value.lower() not in ['direct_phd', 'phd']:
                        eligible_for_category = False
                
                if not eligible_for_category and not self._should_bypass_application_period():
                    logger.info(f"Skipping {scholarship.name}: Student type {student_type.value} not eligible for category {scholarship.category}")
                    continue
                
                # Check whitelist eligibility - PRIMARY REQUIREMENT
                if not self._should_bypass_whitelist():
                    if scholarship.whitelist_enabled:
                        # If whitelist is enabled, student must be in the whitelist
                        if not scholarship.whitelist_student_ids or student.id not in scholarship.whitelist_student_ids:
                            logger.info(f"Skipping {scholarship.name}: Student {student.std_stdcode} not in whitelist (whitelist enabled but student not found)")
                            continue
                        else:
                            logger.info(f"Student {student.std_stdcode} found in whitelist for {scholarship.name}")
                    else:
                        logger.info(f"Scholarship {scholarship.name}: Whitelist not enabled, allowing all students")
                elif self._should_bypass_whitelist():
                    logger.info(f"DEV MODE: Bypassing whitelist check for {scholarship.name}")
                
                # For now, we'll skip complex term count requirements since we don't have external API integration yet
                logger.info(f"Student has {completed_terms} completed terms")
                
                # If all checks pass, add to eligible scholarships
                logger.info(f"Scholarship {scholarship.name} is eligible!")
                eligible_scholarships.append(scholarship)
            except ValidationError as e:
                logger.error(f"Validation error for scholarship {scholarship.name}: {str(e)}")
                continue
        
        logger.info(f"Found {len(eligible_scholarships)} eligible scholarships")
        return eligible_scholarships


class ScholarshipApplicationService:
    """Comprehensive service for managing scholarship applications and workflows"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_application(
        self,
        user_id: int,
        student_id: int,
        scholarship_type_id: int,
        scholarship_type_code: str,
        semester: str,
        academic_year: str,
        application_data: Dict[str, Any],
        is_renewal: bool = False,
        previous_application_id: Optional[int] = None
    ) -> Tuple[Application, str]:
        """Create a new scholarship application using existing schema"""
        
        # Validate eligibility
        scholarship_type = self.db.query(ScholarshipType).filter(
            ScholarshipType.id == scholarship_type_id
        ).first()
        
        if not scholarship_type:
            raise ValueError("Invalid scholarship type")
        
        can_apply, error_msg = scholarship_type.can_student_apply(student_id, semester)
        if not can_apply:
            raise ValueError(error_msg)
        
        # Check for existing application in the same semester
        existing_app = self.db.query(Application).filter(
            and_(
                Application.student_id == student_id,
                Application.scholarship_type_id == scholarship_type_id,
                Application.semester == semester,
                Application.status.notin_([ApplicationStatus.WITHDRAWN.value, ApplicationStatus.REJECTED.value])
            )
        ).first()
        
        if existing_app:
            raise ValueError("Student already has an active application for this scholarship in this semester")
        
        # Generate application number using existing format
        app_number = self._generate_application_id(academic_year)
        
        # Calculate priority score
        priority_score = self._calculate_initial_priority(is_renewal, student_id)
        
        # Extract main and sub types from scholarship code
        main_type = self._extract_main_type(scholarship_type_code)
        sub_type = self._extract_sub_type(scholarship_type_code)
        
        # Create application using existing schema
        application = Application(
            app_id=app_number,
            user_id=user_id,
            student_id=student_id,
            scholarship_type_id=scholarship_type_id,
            scholarship_type=scholarship_type_code,
            scholarship_name=scholarship_type.name,
            main_scholarship_type=main_type,
            sub_scholarship_type=sub_type,
            semester=semester,
            academic_year=academic_year,
            is_renewal=is_renewal,
            previous_application_id=previous_application_id,
            status=ApplicationStatus.DRAFT.value,
            priority_score=priority_score,
            amount=application_data.get('requested_amount'),
            form_data=application_data
        )
        
        self.db.add(application)
        self.db.commit()
        self.db.refresh(application)
        
        return application, "Application created successfully"
    
    def submit_application(self, application_id: int) -> Tuple[bool, str]:
        """Submit application for review"""
        application = self.db.query(Application).filter(
            Application.id == application_id
        ).first()
        
        if not application:
            return False, "Application not found"
        
        if application.status != ApplicationStatus.DRAFT.value:
            return False, "Application is not in draft status"
        
        # Validate required documents
        validation_result = self._validate_application_documents(application)
        if not validation_result[0]:
            return False, validation_result[1]
        
        # Update application status
        application.status = ApplicationStatus.SUBMITTED.value
        application.submitted_at = datetime.now(timezone.utc)
        
        # Set review deadline (30 days from submission)
        application.review_deadline = datetime.now(timezone.utc) + timedelta(days=30)
        
        # Create initial review record
        self._create_initial_review(application)
        
        # If requires professor recommendation, create professor review
        if application.scholarship_type.requires_professor_recommendation:
            self._create_professor_review_request(application)
        
        self.db.commit()
        return True, "Application submitted successfully"
    
    def get_applications_by_priority(
        self,
        scholarship_type_id: Optional[int] = None,
        semester: Optional[str] = None,
        status: Optional[ApplicationStatus] = None,
        limit: int = 100
    ) -> List['Application']:
        """Get applications ordered by priority"""
        query = self.db.query(Application)
        
        if scholarship_type_id:
            query = query.filter(Application.scholarship_type_id == scholarship_type_id)
        
        if semester:
            query = query.filter(Application.semester == semester)
        
        if status:
            query = query.filter(Application.status == status)
        
        # Order by priority score (higher first), then by submission time (earlier first)
        applications = query.order_by(
            desc(Application.priority_score),
            asc(Application.submitted_at)
        ).limit(limit).all()
        
        return applications
    
    def process_renewal_applications_first(self, semester: str) -> Dict[str, int]:
        """Process renewal applications with higher priority"""
        
        # Get all submitted renewal applications for the semester
        renewal_apps = self.db.query(Application).filter(
            and_(
                Application.semester == semester,
                Application.is_renewal == True,
                Application.status == ApplicationStatus.SUBMITTED
            )
        ).order_by(desc(Application.priority_score)).all()
        
        processed_count = 0
        approved_count = 0
        
        for app in renewal_apps:
            # Auto-approve if meets renewal criteria
            if self._meets_renewal_criteria(app):
                app.status = ApplicationStatus.APPROVED
                app.decision_date = datetime.now(timezone.utc)
                approved_count += 1
            else:
                # Move to regular review process
                app.status = ApplicationStatus.UNDER_REVIEW
            
            processed_count += 1
        
        self.db.commit()
        
        return {
            "processed": processed_count,
            "auto_approved": approved_count
        }
    
    def _generate_application_id(self, academic_year: str) -> str:
        """Generate unique application ID using existing format"""
        
        # Get count of applications for this year
        count = self.db.query(Application).filter(
            Application.academic_year == academic_year
        ).count()
        
        # Format: APP-{year}-{count+1:06d}
        return f"APP-{academic_year}-{count+1:06d}"
    
    def _extract_main_type(self, scholarship_code: str) -> str:
        """Extract main scholarship type from code"""
        code_upper = scholarship_code.upper()
        if "UNDERGRADUATE_FRESHMAN" in code_upper:
            return ScholarshipMainType.UNDERGRADUATE_FRESHMAN.value
        elif "DIRECT_PHD" in code_upper:
            return ScholarshipMainType.DIRECT_PHD.value
        elif "PHD" in code_upper:
            return ScholarshipMainType.PHD.value
        return ScholarshipMainType.PHD.value  # Default
    
    def _extract_sub_type(self, scholarship_code: str) -> str:
        """Extract sub scholarship type from code"""
        code_upper = scholarship_code.upper()
        if "NSTC" in code_upper:
            return ScholarshipSubType.NSTC.value
        elif "MOE_1W" in code_upper:
            return ScholarshipSubType.MOE_1W.value
        elif "MOE_2W" in code_upper:
            return ScholarshipSubType.MOE_2W.value
        return ScholarshipSubType.GENERAL.value  # Default
    
    def _calculate_initial_priority(self, is_renewal: bool, student_id: int) -> int:
        """Calculate initial priority score for application"""
        score = 0
        
        # Renewal applications get higher priority
        if is_renewal:
            score += 100
        
        # Add other priority factors here
        # - Academic performance
        # - Previous scholarship history
        # - Financial need assessment
        
        return score
    
    def _validate_application_documents(self, application: 'Application') -> Tuple[bool, str]:
        """Validate that all required documents are uploaded"""
        
        required_docs = application.scholarship_type.required_documents or []
        uploaded_docs = [f.document_type for f in application.files if f.document_type]
        
        missing_docs = []
        for doc_type in required_docs:
            if doc_type not in uploaded_docs:
                missing_docs.append(doc_type)
        
        if missing_docs:
            return False, f"Missing required documents: {', '.join(missing_docs)}"
        
        return True, "All required documents uploaded"
    
    def _create_initial_review(self, application: 'Application') -> 'ApplicationReview':
        """Create initial review record for submitted application"""
        
        review = ApplicationReview(
            application_id=application.id,
            reviewer_id=1,  # System or default reviewer
            review_stage="initial_review",
            status=ReviewStatus.PENDING,
            due_date=application.review_deadline
        )
        
        self.db.add(review)
        return review
    
    def _create_professor_review_request(self, application: 'Application') -> 'ProfessorReview':
        """Create professor review request"""
        
        # In a real implementation, this would determine the appropriate professor
        professor_id = 1  # Placeholder
        
        professor_review = ProfessorReview(
            application_id=application.id,
            professor_id=professor_id,
            review_type="recommendation",
            is_required=True,
            due_date=datetime.now(timezone.utc) + timedelta(days=14),
            status=ReviewStatus.PENDING
        )
        
        self.db.add(professor_review)
        
        # Create standard review items
        review_items = [
            ("academic_performance", "Academic performance and achievements", 5),
            ("research_potential", "Research potential and capability", 5),
            ("overall_recommendation", "Overall recommendation", 5)
        ]
        
        for item_name, description, max_rating in review_items:
            review_item = ProfessorReviewItem(
                professor_review_id=professor_review.id,
                item_name=item_name,
                item_description=description,
                max_rating=max_rating,
                weight=1.0
            )
            self.db.add(review_item)
        
        return professor_review
    
    def _meets_renewal_criteria(self, application: 'Application') -> bool:
        """Check if renewal application meets auto-approval criteria"""
        
        # Implement renewal criteria logic
        # - Maintained minimum GPA
        # - No academic violations
        # - Satisfactory progress
        # - Complete required documents
        
        # For now, return True as placeholder
        return True


class ScholarshipQuotaService:
    """Service for managing scholarship quotas - simplified for existing schema"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_quota_status_by_type(
        self,
        main_scholarship_type: str,
        sub_scholarship_type: str,
        semester: str
    ) -> Dict[str, Any]:
        """Get quota status for a scholarship type combination"""
        
        # Count approved applications by type
        approved_count = self.db.query(Application).filter(
            and_(
                Application.main_scholarship_type == main_scholarship_type,
                Application.sub_scholarship_type == sub_scholarship_type,
                Application.semester == semester,
                Application.status == ApplicationStatus.APPROVED.value
            )
        ).count()
        
        # Get pending applications
        pending_count = self.db.query(Application).filter(
            and_(
                Application.main_scholarship_type == main_scholarship_type,
                Application.sub_scholarship_type == sub_scholarship_type,
                Application.semester == semester,
                Application.status.in_([
                    ApplicationStatus.SUBMITTED.value,
                    ApplicationStatus.UNDER_REVIEW.value
                ])
            )
        ).count()
        
        # For now, use default quotas (these would come from configuration)
        default_quotas = {
            (ScholarshipMainType.PHD.value, ScholarshipSubType.NSTC.value): 50,
            (ScholarshipMainType.PHD.value, ScholarshipSubType.GENERAL.value): 30,
            (ScholarshipMainType.DIRECT_PHD.value, ScholarshipSubType.NSTC.value): 40,
            (ScholarshipMainType.UNDERGRADUATE_FRESHMAN.value, ScholarshipSubType.GENERAL.value): 100,
        }
        
        total_quota = default_quotas.get((main_scholarship_type, sub_scholarship_type), 20)
        
        return {
            "main_type": main_scholarship_type,
            "sub_type": sub_scholarship_type,
            "semester": semester,
            "total_quota": total_quota,
            "total_used": approved_count,
            "total_available": total_quota - approved_count,
            "pending": pending_count,
            "usage_percent": (approved_count / total_quota * 100) if total_quota > 0 else 0
        }
    
    def process_applications_by_priority(
        self,
        main_scholarship_type: str,
        sub_scholarship_type: str,
        semester: str
    ) -> Dict[str, int]:
        """Process applications by priority within quota limits"""
        
        quota_status = self.get_quota_status_by_type(main_scholarship_type, sub_scholarship_type, semester)
        
        if quota_status["total_available"] <= 0:
            return {"processed": 0, "approved": 0, "message": "No remaining quota"}
        
        # Get applications ordered by priority (renewal first, then by submission time)
        applications = self.db.query(Application).filter(
            and_(
                Application.main_scholarship_type == main_scholarship_type,
                Application.sub_scholarship_type == sub_scholarship_type,
                Application.semester == semester,
                Application.status.in_([
                    ApplicationStatus.SUBMITTED.value,
                    ApplicationStatus.UNDER_REVIEW.value
                ])
            )
        ).order_by(
            desc(Application.is_renewal),  # Renewals first
            desc(Application.priority_score),
            asc(Application.submitted_at)
        ).all()
        
        processed_count = 0
        approved_count = 0
        remaining_quota = quota_status["total_available"]
        
        for app in applications:
            processed_count += 1
            
            if remaining_quota > 0:
                # Approve within quota
                app.status = ApplicationStatus.APPROVED.value
                app.decision_date = datetime.now(timezone.utc)
                approved_count += 1
                remaining_quota -= 1
            else:
                # Reject due to quota limit
                app.status = ApplicationStatus.REJECTED.value
                app.rejection_reason = "Quota limit reached"
                app.decision_date = datetime.now(timezone.utc)
        
        self.db.commit()
        
        return {
            "processed": processed_count,
            "approved": approved_count,
            "rejected": processed_count - approved_count,
            "remaining_quota": remaining_quota
        } 