"""
Test renewal flow sequence - ensuring renewal process completes before general process starts
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.models.scholarship import ScholarshipType, ScholarshipStatus, ScholarshipCategory
from app.models.enums import Semester, SubTypeSelectionMode, ApplicationCycle


class TestRenewalFlowSequence:
    """Test that renewal flow completes before general flow starts"""
    
    @pytest.fixture
    def scholarship_with_sequential_flow(self):
        """Create a scholarship with sequential renewal and general flows"""
        now = datetime.now(timezone.utc)
        
        return ScholarshipType(
            code="SEQUENTIAL_SCHOLARSHIP",
            name="順序流程獎學金",
            category=ScholarshipCategory.PHD.value,
            academic_year=113,
            semester=Semester.FIRST,
            amount=50000,
            status=ScholarshipStatus.ACTIVE.value,
            
            # 續領申請期間（優先處理）
            renewal_application_start_date=now - timedelta(days=60),
            renewal_application_end_date=now - timedelta(days=40),
            
            # 續領審查期間
            renewal_professor_review_start=now - timedelta(days=39),
            renewal_professor_review_end=now - timedelta(days=30),
            renewal_college_review_start=now - timedelta(days=29),
            renewal_college_review_end=now - timedelta(days=20),
            
            # 一般申請期間（續領流程完全結束後）
            application_start_date=now - timedelta(days=15),
            application_end_date=now + timedelta(days=15),
            
            # 一般申請審查期間
            professor_review_start=now + timedelta(days=16),
            professor_review_end=now + timedelta(days=30),
            college_review_start=now + timedelta(days=31),
            college_review_end=now + timedelta(days=45),
        )
    
    def test_renewal_flow_completes_before_general_starts(self, scholarship_with_sequential_flow):
        """Test that renewal flow completes before general application starts"""
        # 驗證續領學院審查結束時間早於一般申請開始時間
        assert scholarship_with_sequential_flow.renewal_college_review_end < scholarship_with_sequential_flow.application_start_date
        
        # 驗證續領教授審查結束時間早於續領學院審查開始時間
        assert scholarship_with_sequential_flow.renewal_professor_review_end < scholarship_with_sequential_flow.renewal_college_review_start
        
        # 驗證續領申請結束時間早於續領教授審查開始時間
        assert scholarship_with_sequential_flow.renewal_application_end_date < scholarship_with_sequential_flow.renewal_professor_review_start
    
    def test_no_overlap_between_renewal_and_general_periods(self, scholarship_with_sequential_flow):
        """Test that there's no overlap between renewal and general periods"""
        # 續領申請期間和一般申請期間不重疊
        assert scholarship_with_sequential_flow.renewal_application_end_date < scholarship_with_sequential_flow.application_start_date
        
        # 續領學院審查期間和一般申請期間不重疊
        assert scholarship_with_sequential_flow.renewal_college_review_end < scholarship_with_sequential_flow.application_start_date
    
    def test_sequential_review_stages(self, scholarship_with_sequential_flow):
        """Test that review stages follow the correct sequence"""
        now = datetime.now(timezone.utc)
        
        # 測試不同時間點的審查階段
        # 1. 續領申請期間
        test_time = now - timedelta(days=50)
        scholarship_with_sequential_flow.renewal_application_start_date = test_time - timedelta(days=5)
        scholarship_with_sequential_flow.renewal_application_end_date = test_time + timedelta(days=5)
        scholarship_with_sequential_flow.application_start_date = test_time + timedelta(days=20)
        
        # 2. 續領教授審查期間
        test_time = now - timedelta(days=35)
        scholarship_with_sequential_flow.renewal_application_end_date = test_time - timedelta(days=1)
        scholarship_with_sequential_flow.renewal_professor_review_start = test_time - timedelta(days=5)
        scholarship_with_sequential_flow.renewal_professor_review_end = test_time + timedelta(days=5)
        scholarship_with_sequential_flow.renewal_college_review_start = test_time + timedelta(days=10)
        
        # 3. 續領學院審查期間
        test_time = now - timedelta(days=25)
        scholarship_with_sequential_flow.renewal_professor_review_end = test_time - timedelta(days=1)
        scholarship_with_sequential_flow.renewal_college_review_start = test_time - timedelta(days=5)
        scholarship_with_sequential_flow.renewal_college_review_end = test_time + timedelta(days=5)
        scholarship_with_sequential_flow.application_start_date = test_time + timedelta(days=10)
        
        # 4. 一般申請期間
        test_time = now - timedelta(days=10)
        scholarship_with_sequential_flow.renewal_college_review_end = test_time - timedelta(days=1)
        scholarship_with_sequential_flow.application_start_date = test_time - timedelta(days=5)
        scholarship_with_sequential_flow.application_end_date = test_time + timedelta(days=5)
        scholarship_with_sequential_flow.professor_review_start = test_time + timedelta(days=10)
    
    def test_application_eligibility_sequence(self, scholarship_with_sequential_flow):
        """Test application eligibility based on current period"""
        from app.models.application import Application
        
        # 模擬現有申請列表
        existing_applications = []
        
        # 在續領期間，只能申請續領
        now = datetime.now(timezone.utc)
        scholarship_with_sequential_flow.renewal_application_start_date = now - timedelta(days=5)
        scholarship_with_sequential_flow.renewal_application_end_date = now + timedelta(days=5)
        scholarship_with_sequential_flow.application_start_date = now + timedelta(days=20)
        
        # 檢查續領申請資格
        can_renewal = scholarship_with_sequential_flow.can_student_apply_renewal(1, existing_applications)
        assert can_renewal is True
        
        # 檢查一般申請資格（應該被拒絕，因為還不是一般申請期間）
        can_general = scholarship_with_sequential_flow.can_student_apply_general(1, existing_applications)
        assert can_general is False
        
        # 在一般申請期間，只能申請一般申請
        scholarship_with_sequential_flow.renewal_application_end_date = now - timedelta(days=1)
        scholarship_with_sequential_flow.application_start_date = now - timedelta(days=5)
        scholarship_with_sequential_flow.application_end_date = now + timedelta(days=5)
        
        # 檢查續領申請資格（應該被拒絕，因為續領期間已結束）
        can_renewal = scholarship_with_sequential_flow.can_student_apply_renewal(1, existing_applications)
        assert can_renewal is False
        
        # 檢查一般申請資格
        can_general = scholarship_with_sequential_flow.can_student_apply_general(1, existing_applications)
        assert can_general is True 