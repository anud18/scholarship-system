"""
Comprehensive tests for EligibilityService
Target: 0% → 80% coverage
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.services.eligibility_service import EligibilityService


class TestEligibilityServiceDevMode:
    """Test development mode bypass features"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return EligibilityService(db)

    def test_is_dev_mode_debug_true(self, service):
        """Test dev mode detection with debug=True"""
        with patch("app.services.eligibility_service.settings") as mock_settings:
            mock_settings.debug = True
            mock_settings.environment = "production"
            assert service._is_dev_mode()

    def test_is_dev_mode_environment_development(self, service):
        """Test dev mode detection with environment=development"""
        with patch("app.services.eligibility_service.settings") as mock_settings:
            mock_settings.debug = False
            mock_settings.environment = "development"
            assert service._is_dev_mode()

    def test_is_dev_mode_production(self, service):
        """Test dev mode detection in production"""
        with patch("app.services.eligibility_service.settings") as mock_settings:
            mock_settings.debug = False
            mock_settings.environment = "production"
            assert not service._is_dev_mode()

    def test_should_bypass_whitelist_dev_enabled(self, service):
        """Test whitelist bypass in dev mode"""
        with patch("app.services.eligibility_service.settings") as mock_settings, patch(
            "app.services.eligibility_service.DEV_SCHOLARSHIP_SETTINGS",
            {"BYPASS_WHITELIST": True},
        ):
            mock_settings.debug = True
            assert service._should_bypass_whitelist()

    def test_should_bypass_whitelist_dev_disabled(self, service):
        """Test whitelist bypass disabled"""
        with patch("app.services.eligibility_service.settings") as mock_settings, patch(
            "app.services.eligibility_service.DEV_SCHOLARSHIP_SETTINGS",
            {"BYPASS_WHITELIST": False},
        ):
            mock_settings.debug = True
            assert not service._should_bypass_whitelist()

    def test_should_bypass_application_period_enabled(self, service):
        """Test application period bypass in dev mode"""
        with patch("app.services.eligibility_service.settings") as mock_settings, patch(
            "app.services.eligibility_service.DEV_SCHOLARSHIP_SETTINGS",
            {"ALWAYS_OPEN_APPLICATION": True},
        ):
            mock_settings.debug = True
            assert service._should_bypass_application_period()


@pytest.mark.asyncio
class TestEligibilityServiceBasicChecks:
    """Test basic eligibility checks"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return EligibilityService(db)

    @pytest.fixture
    def mock_scholarship_type(self):
        return Mock(spec=ScholarshipType, id=1, code="test_scholarship", whitelist_enabled=False)

    @pytest.fixture
    def active_config(self, mock_scholarship_type):
        """Create active scholarship configuration"""
        config = Mock(spec=ScholarshipConfiguration)
        config.is_active = True
        config.is_effective = True
        config.scholarship_type = mock_scholarship_type
        config.application_start_date = datetime.now(timezone.utc) - timedelta(days=7)
        config.application_end_date = datetime.now(timezone.utc) + timedelta(days=7)
        config.renewal_application_start_date = None
        config.renewal_application_end_date = None
        config.whitelist_student_ids = None
        return config

    @pytest.fixture
    def student_data(self):
        return {"std_stdcode": "112550001", "std_gpa": 3.5, "std_name": "Test Student"}

    async def test_check_inactive_configuration(self, service, active_config, student_data):
        """Test eligibility check fails for inactive configuration"""
        active_config.is_active = False

        with patch.object(service, "_should_bypass_application_period", return_value=False):
            is_eligible, reasons = await service.check_student_eligibility(student_data, active_config)

        assert not is_eligible
        assert "獎學金配置未啟用" in reasons

    async def test_check_ineffective_configuration(self, service, active_config, student_data):
        """Test eligibility check fails for ineffective configuration"""
        active_config.is_effective = False

        with patch.object(service, "_should_bypass_application_period", return_value=False):
            is_eligible, reasons = await service.check_student_eligibility(student_data, active_config)

        assert not is_eligible
        assert "不在獎學金有效期間內" in reasons

    async def test_check_outside_application_period(self, service, active_config, student_data):
        """Test eligibility check fails outside application period"""
        active_config.application_start_date = datetime.now(timezone.utc) - timedelta(days=30)
        active_config.application_end_date = datetime.now(timezone.utc) - timedelta(days=1)

        with patch.object(service, "_should_bypass_application_period", return_value=False), patch.object(
            service, "_check_scholarship_rules", return_value=(True, [])
        ):
            is_eligible, reasons = await service.check_student_eligibility(student_data, active_config)

        assert not is_eligible
        assert "不在申請期間內" in reasons

    async def test_check_within_application_period(self, service, active_config, student_data):
        """Test eligibility check passes within application period"""
        with patch.object(service, "_should_bypass_application_period", return_value=False), patch.object(
            service, "_check_scholarship_rules", return_value=(True, [])
        ):
            is_eligible, reasons = await service.check_student_eligibility(student_data, active_config)

        assert is_eligible
        assert len(reasons) == 0

    async def test_check_within_renewal_period(self, service, active_config, student_data):
        """Test eligibility check passes within renewal period"""
        # Main period expired
        active_config.application_start_date = datetime.now(timezone.utc) - timedelta(days=30)
        active_config.application_end_date = datetime.now(timezone.utc) - timedelta(days=10)

        # But renewal period is active
        active_config.renewal_application_start_date = datetime.now(timezone.utc) - timedelta(days=5)
        active_config.renewal_application_end_date = datetime.now(timezone.utc) + timedelta(days=5)

        with patch.object(service, "_should_bypass_application_period", return_value=False), patch.object(
            service, "_check_scholarship_rules", return_value=(True, [])
        ):
            is_eligible, reasons = await service.check_student_eligibility(student_data, active_config)

        assert is_eligible
        assert len(reasons) == 0

    async def test_check_bypass_application_period(self, service, active_config, student_data):
        """Test application period bypass in dev mode"""
        # Set expired period
        active_config.application_start_date = datetime.now(timezone.utc) - timedelta(days=30)
        active_config.application_end_date = datetime.now(timezone.utc) - timedelta(days=1)

        with patch.object(service, "_should_bypass_application_period", return_value=True), patch.object(
            service, "_check_scholarship_rules", return_value=(True, [])
        ):
            is_eligible, reasons = await service.check_student_eligibility(student_data, active_config)

        assert is_eligible
        assert len(reasons) == 0


@pytest.mark.asyncio
class TestEligibilityServiceWhitelist:
    """Test whitelist functionality"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return EligibilityService(db)

    @pytest.fixture
    def whitelist_config(self):
        """Create whitelist-enabled configuration"""
        config = Mock(spec=ScholarshipConfiguration)
        config.is_active = True
        config.is_effective = True
        config.scholarship_type = Mock(whitelist_enabled=True)
        config.application_start_date = datetime.now(timezone.utc) - timedelta(days=7)
        config.application_end_date = datetime.now(timezone.utc) + timedelta(days=7)
        config.renewal_application_start_date = None
        config.renewal_application_end_date = None
        config.whitelist_student_ids = {"112550001": True, "112550002": True}
        return config

    async def test_whitelist_student_allowed_dict(self, service, whitelist_config):
        """Test whitelist allows listed student (dict format)"""
        student_data = {"std_stdcode": "112550001"}

        with patch.object(service, "_should_bypass_application_period", return_value=False), patch.object(
            service, "_should_bypass_whitelist", return_value=False
        ), patch.object(service, "_check_scholarship_rules", return_value=(True, [])):
            is_eligible, reasons = await service.check_student_eligibility(student_data, whitelist_config)

        assert is_eligible
        assert len(reasons) == 0

    async def test_whitelist_student_denied_dict(self, service, whitelist_config):
        """Test whitelist denies unlisted student (dict format)"""
        student_data = {"std_stdcode": "112550999"}

        with patch.object(service, "_should_bypass_application_period", return_value=False), patch.object(
            service, "_should_bypass_whitelist", return_value=False
        ), patch.object(service, "_check_scholarship_rules", return_value=(True, [])):
            is_eligible, reasons = await service.check_student_eligibility(student_data, whitelist_config)

        assert not is_eligible
        assert "未在白名單中" in reasons

    async def test_whitelist_student_allowed_list(self, service, whitelist_config):
        """Test whitelist allows listed student (list format)"""
        whitelist_config.whitelist_student_ids = ["112550001", "112550002"]
        student_data = {"std_stdcode": "112550001"}

        with patch.object(service, "_should_bypass_application_period", return_value=False), patch.object(
            service, "_should_bypass_whitelist", return_value=False
        ), patch.object(service, "_check_scholarship_rules", return_value=(True, [])):
            is_eligible, reasons = await service.check_student_eligibility(student_data, whitelist_config)

        assert is_eligible
        assert len(reasons) == 0

    async def test_whitelist_bypass(self, service, whitelist_config):
        """Test whitelist bypass in dev mode"""
        student_data = {"std_stdcode": "112550999"}  # Not in whitelist

        with patch.object(service, "_should_bypass_application_period", return_value=False), patch.object(
            service, "_should_bypass_whitelist", return_value=True
        ), patch.object(service, "_check_scholarship_rules", return_value=(True, [])):
            is_eligible, reasons = await service.check_student_eligibility(student_data, whitelist_config)

        assert is_eligible
        assert len(reasons) == 0


@pytest.mark.asyncio
class TestEligibilityServiceDetailedCheck:
    """Test detailed eligibility check with rule breakdown"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return EligibilityService(db)

    @pytest.fixture
    def active_config(self):
        config = Mock(spec=ScholarshipConfiguration)
        config.is_active = True
        config.is_effective = True
        config.scholarship_type = Mock(whitelist_enabled=False)
        config.application_start_date = datetime.now(timezone.utc) - timedelta(days=7)
        config.application_end_date = datetime.now(timezone.utc) + timedelta(days=7)
        config.renewal_application_start_date = None
        config.renewal_application_end_date = None
        config.whitelist_student_ids = None
        return config

    async def test_detailed_check_success(self, service, active_config):
        """Test detailed eligibility check returns details"""
        student_data = {"std_stdcode": "112550001"}

        mock_details = {
            "passed": [{"rule": "GPA >= 3.0", "tag": "academic"}],
            "warnings": [],
            "errors": [],
        }

        with patch.object(service, "_should_bypass_application_period", return_value=False), patch.object(
            service,
            "_check_scholarship_rules_detailed",
            return_value=(True, [], mock_details),
        ):
            (
                is_eligible,
                reasons,
                details,
            ) = await service.get_detailed_eligibility_check(student_data, active_config)

        assert is_eligible
        assert len(reasons) == 0
        assert "passed" in details
        assert "warnings" in details
        assert "errors" in details

    async def test_detailed_check_inactive(self, service, active_config):
        """Test detailed check fails for inactive config"""
        active_config.is_active = False
        student_data = {"std_stdcode": "112550001"}

        with patch.object(service, "_should_bypass_application_period", return_value=False):
            (
                is_eligible,
                reasons,
                details,
            ) = await service.get_detailed_eligibility_check(student_data, active_config)

        assert not is_eligible
        assert "獎學金配置未啟用" in reasons
        assert details == {"passed": [], "warnings": [], "errors": []}
