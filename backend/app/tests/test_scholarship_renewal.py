"""
Test scholarship renewal application period functionality
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.models.scholarship import ScholarshipType, ScholarshipStatus, ScholarshipCategory
from app.models.enums import Semester, SubTypeSelectionMode, CycleType


class TestScholarshipRenewalPeriod:
    """Test scholarship renewal application period functionality"""
    
    @pytest.fixture
    def scholarship_with_renewal(self):
        """Create a scholarship with renewal periods"""
        now = datetime.now(timezone.utc)
        
        return ScholarshipType(
            code="TEST_SCHOLARSHIP",
            name="測試獎學金",
            category=ScholarshipCategory.PHD.value,
            academic_year=113,
            semester=Semester.FIRST,
            amount=50000,
            status=ScholarshipStatus.ACTIVE.value,
            
            # 續領申請期間（優先處理）
            renewal_application_start_date=now - timedelta(days=10),
            renewal_application_end_date=now + timedelta(days=5),
            
            # 一般申請期間（續領處理完畢後）
            application_start_date=now + timedelta(days=6),
            application_end_date=now + timedelta(days=20),
            
            # 續領審查期間
            renewal_professor_review_start=now + timedelta(days=6),
            renewal_professor_review_end=now + timedelta(days=10),
            renewal_college_review_start=now + timedelta(days=11),
            renewal_college_review_end=now + timedelta(days=15),
            
            # 一般申請審查期間
            professor_review_start=now + timedelta(days=21),
            professor_review_end=now + timedelta(days=25),
            college_review_start=now + timedelta(days=26),
            college_review_end=now + timedelta(days=30),
        )
    
    def test_renewal_application_period_detection(self, scholarship_with_renewal):
        """Test renewal application period detection"""
        # 現在應該在續領申請期間
        assert scholarship_with_renewal.is_renewal_application_period is True
        assert scholarship_with_renewal.is_general_application_period is False
        assert scholarship_with_renewal.is_application_period is True
        assert scholarship_with_renewal.current_application_type == "renewal"
    
    def test_general_application_period_detection(self, scholarship_with_renewal):
        """Test general application period detection"""
        # 設定時間到一般申請期間
        now = datetime.now(timezone.utc)
        scholarship_with_renewal.renewal_application_end_date = now - timedelta(days=1)
        scholarship_with_renewal.application_start_date = now - timedelta(days=1)
        scholarship_with_renewal.application_end_date = now + timedelta(days=10)
        
        assert scholarship_with_renewal.is_renewal_application_period is False
        assert scholarship_with_renewal.is_general_application_period is True
        assert scholarship_with_renewal.is_application_period is True
        assert scholarship_with_renewal.current_application_type == "general"
    
    def test_no_application_period(self, scholarship_with_renewal):
        """Test when not in any application period"""
        # 設定時間到申請期間之外
        now = datetime.now(timezone.utc)
        scholarship_with_renewal.renewal_application_end_date = now - timedelta(days=10)
        scholarship_with_renewal.application_start_date = now + timedelta(days=10)
        
        assert scholarship_with_renewal.is_renewal_application_period is False
        assert scholarship_with_renewal.is_general_application_period is False
        assert scholarship_with_renewal.is_application_period is False
        assert scholarship_with_renewal.current_application_type is None
    
    def test_review_stage_detection(self, scholarship_with_renewal):
        """Test review stage detection"""
        now = datetime.now(timezone.utc)
        
        # 測試續領教授審查期間
        scholarship_with_renewal.renewal_application_end_date = now - timedelta(days=1)
        scholarship_with_renewal.renewal_professor_review_start = now - timedelta(days=1)
        scholarship_with_renewal.renewal_professor_review_end = now + timedelta(days=5)
        
        assert scholarship_with_renewal.get_current_review_stage() == "renewal_professor"
        
        # 測試續領學院審查期間
        scholarship_with_renewal.renewal_professor_review_end = now - timedelta(days=1)
        scholarship_with_renewal.renewal_college_review_start = now - timedelta(days=1)
        scholarship_with_renewal.renewal_college_review_end = now + timedelta(days=5)
        
        assert scholarship_with_renewal.get_current_review_stage() == "renewal_college"
        
        # 測試一般教授審查期間
        scholarship_with_renewal.renewal_college_review_end = now - timedelta(days=1)
        scholarship_with_renewal.application_end_date = now - timedelta(days=1)
        scholarship_with_renewal.professor_review_start = now - timedelta(days=1)
        scholarship_with_renewal.professor_review_end = now + timedelta(days=5)
        
        assert scholarship_with_renewal.get_current_review_stage() == "general_professor"
        
        # 測試一般學院審查期間
        scholarship_with_renewal.professor_review_end = now - timedelta(days=1)
        scholarship_with_renewal.college_review_start = now - timedelta(days=1)
        scholarship_with_renewal.college_review_end = now + timedelta(days=5)
        
        assert scholarship_with_renewal.get_current_review_stage() == "general_college"
    
    def test_application_timeline(self, scholarship_with_renewal):
        """Test application timeline generation"""
        timeline = scholarship_with_renewal.get_application_timeline()
        
        assert "renewal" in timeline
        assert "general" in timeline
        assert timeline["renewal"]["application_start"] == scholarship_with_renewal.renewal_application_start_date
        assert timeline["renewal"]["application_end"] == scholarship_with_renewal.renewal_application_end_date
        assert timeline["general"]["application_start"] == scholarship_with_renewal.application_start_date
        assert timeline["general"]["application_end"] == scholarship_with_renewal.application_end_date
    
    def test_next_deadline(self, scholarship_with_renewal):
        """Test next deadline calculation"""
        now = datetime.now(timezone.utc)
        
        # 設定續領申請截止日期為最近
        scholarship_with_renewal.renewal_application_end_date = now + timedelta(days=2)
        scholarship_with_renewal.renewal_professor_review_end = now + timedelta(days=5)
        scholarship_with_renewal.application_end_date = now + timedelta(days=10)
        
        next_deadline = scholarship_with_renewal.get_next_deadline()
        assert next_deadline == scholarship_with_renewal.renewal_application_end_date


class TestApplicationRenewal:
    """Test application renewal functionality"""
    
    def test_renewal_application_properties(self):
        """Test renewal application properties"""
        from app.models.application import Application, ApplicationStatus
        
        # 測試續領申請
        renewal_app = Application(
            app_id="APP-2025-000001",
            user_id=1,
            student_id=1,
            scholarship_type_id=1,
            is_renewal=True,
            academic_year=113,
            semester=Semester.FIRST,
            status=ApplicationStatus.SUBMITTED.value
        )
        
        assert renewal_app.is_renewal_application is True
        assert renewal_app.is_general_application is False
        assert renewal_app.application_type_label == "續領申請"
        assert renewal_app.get_review_stage() == "renewal_professor"
        
        # 測試一般申請
        general_app = Application(
            app_id="APP-2025-000002",
            user_id=2,
            student_id=2,
            scholarship_type_id=1,
            is_renewal=False,
            academic_year=113,
            semester=Semester.FIRST,
            status=ApplicationStatus.SUBMITTED.value
        )
        
        assert general_app.is_renewal_application is False
        assert general_app.is_general_application is True
        assert general_app.application_type_label == "一般申請"
        assert general_app.get_review_stage() == "general_professor" 