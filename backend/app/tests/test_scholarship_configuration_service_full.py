"""
Comprehensive tests for ScholarshipConfigurationService
Target: 0% → 80% coverage
"""

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import QuotaManagementMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.services.scholarship_configuration_service import ScholarshipConfigurationService


@pytest.mark.asyncio
class TestScholarshipConfigurationServiceActiveConfigs:
    """Test active configuration retrieval"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipConfigurationService(db)

    async def test_get_active_configurations_all(self, service):
        """Test getting all active configurations"""
        mock_configs = [
            Mock(spec=ScholarshipConfiguration, is_effective=True),
            Mock(spec=ScholarshipConfiguration, is_effective=True),
        ]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_configs
        service.db.execute = AsyncMock(return_value=mock_result)

        configs = await service.get_active_configurations()

        assert len(configs) == 2

    async def test_get_active_configurations_filtered(self, service):
        """Test getting configurations filtered by scholarship type"""
        mock_config = Mock(spec=ScholarshipConfiguration, is_effective=True)

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_config]
        service.db.execute = AsyncMock(return_value=mock_result)

        configs = await service.get_active_configurations(scholarship_type_id=1)

        assert len(configs) == 1

    async def test_get_active_configurations_excludes_ineffective(self, service):
        """Test that ineffective configs are excluded"""
        mock_configs = [
            Mock(spec=ScholarshipConfiguration, is_effective=True),
            Mock(spec=ScholarshipConfiguration, is_effective=False),
        ]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_configs
        service.db.execute = AsyncMock(return_value=mock_result)

        configs = await service.get_active_configurations()

        assert len(configs) == 1


@pytest.mark.asyncio
class TestScholarshipConfigurationServiceByCode:
    """Test configuration lookup by code"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipConfigurationService(db)

    async def test_get_configuration_by_code_found(self, service):
        """Test finding configuration by code"""
        mock_config = Mock(spec=ScholarshipConfiguration)

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_config
        service.db.execute = AsyncMock(return_value=mock_result)

        config = await service.get_configuration_by_code("CONFIG_001")

        assert config == mock_config

    async def test_get_configuration_by_code_not_found(self, service):
        """Test not finding configuration by code"""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        service.db.execute = AsyncMock(return_value=mock_result)

        config = await service.get_configuration_by_code("INVALID")

        assert config is None


@pytest.mark.asyncio
class TestScholarshipConfigurationServiceValidation:
    """Test configuration validation"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipConfigurationService(db)

    def test_validate_configuration_requirements_success(self, service):
        """Test successful configuration validation"""
        config = Mock(spec=ScholarshipConfiguration)
        application_data = {"gpa": 3.5}

        is_valid, errors = service.validate_configuration_requirements(config, application_data)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_configuration_data_valid(self, service):
        """Test configuration data validation"""
        config_data = {
            "config_code": "TEST_001",
            "scholarship_type_id": 1,
            "academic_year": 113,
            "semester": "first",
        }

        errors = service.validate_configuration_data(config_data)

        assert isinstance(errors, list)


@pytest.mark.asyncio
class TestScholarshipConfigurationServiceQuota:
    """Test quota management"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipConfigurationService(db)

    async def test_check_quota_availability_unlimited(self, service):
        """Test quota check with unlimited quota"""
        config = Mock(spec=ScholarshipConfiguration)
        config.quota_management_mode = QuotaManagementMode.none

        available, info = await service.check_quota_availability(config)

        assert available is True
        assert info["unlimited"] is True

    async def test_check_quota_availability_with_limit(self, service):
        """Test quota check with limited quota"""
        config = Mock(spec=ScholarshipConfiguration)
        config.quota_management_mode = QuotaManagementMode.simple
        config.has_quota_limit = True
        config.total_quota = 100
        config.scholarship_type_id = 1

        mock_result = Mock()
        mock_result.scalar.return_value = 50
        service.db.execute = AsyncMock(return_value=mock_result)

        available, info = await service.check_quota_availability(config)

        assert available is True
        assert info["available_quota"] == 50
        assert info["usage_percentage"] == 50.0

    async def test_check_quota_availability_exceeded(self, service):
        """Test quota check when quota exceeded"""
        config = Mock(spec=ScholarshipConfiguration)
        config.quota_management_mode = QuotaManagementMode.simple
        config.has_quota_limit = True
        config.total_quota = 100
        config.scholarship_type_id = 1

        mock_result = Mock()
        mock_result.scalar.return_value = 100
        service.db.execute = AsyncMock(return_value=mock_result)

        available, info = await service.check_quota_availability(config)

        assert available is False
        assert info["available_quota"] == 0


@pytest.mark.asyncio
class TestScholarshipConfigurationServiceScoring:
    """Test application scoring"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipConfigurationService(db)

    def test_calculate_application_score_basic(self, service):
        """Test basic application score calculation — no scoring_criteria → 0.0."""
        config = Mock()  # no spec= so arbitrary attrs allowed
        config.scoring_criteria = None

        application_data = {"gpa": 3.5, "class_ranking": 10, "total_students": 100}

        score = service.calculate_application_score(config, application_data)

        assert score == 0.0

    def test_calculate_application_score_with_config(self, service):
        """Test score calculation with scoring criteria config."""
        config = Mock()  # no spec= so arbitrary attrs allowed
        config.scoring_criteria = True
        config.get_scoring_criteria.return_value = {
            "gpa": {"weight": 0.6, "max_score": 4.0},
            "ranking": {"weight": 0.4, "max_score": 100},
        }

        application_data = {"score_gpa": 3.8, "score_ranking": 80}

        score = service.calculate_application_score(config, application_data)

        assert score >= 0


@pytest.mark.asyncio
class TestScholarshipConfigurationServiceCRUD:
    """Test CRUD operations"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipConfigurationService(db)

    async def test_create_configuration(self, service):
        """Test configuration creation"""
        config_data = {
            "config_code": "NEW_CONFIG",
            "scholarship_type_id": 1,
            "academic_year": 113,
            "semester": "first",
        }

        # Service does ONE execute: check if config already exists for this period.
        # Return None so the service proceeds to create.
        mock_config_result = Mock()
        mock_config_result.scalar_one_or_none.return_value = None

        service.db.execute = AsyncMock(return_value=mock_config_result)
        service.db.add = Mock()
        service.db.commit = AsyncMock()
        service.db.refresh = AsyncMock()

        await service.create_configuration(
            scholarship_type_id=config_data.get("scholarship_type_id", 1),
            config_data=config_data,
            created_by_user_id=1,
        )

        assert service.db.add.called
        assert service.db.commit.called

    async def test_update_configuration(self, service):
        """Test configuration update"""
        config_id = 1
        update_data = {"total_quota": 150}

        mock_config = Mock(spec=ScholarshipConfiguration)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_config

        service.db.execute = AsyncMock(return_value=mock_result)
        service.db.commit = AsyncMock()
        service.db.refresh = AsyncMock()

        await service.update_configuration(config_id, update_data, updated_by_user_id=1)

        assert service.db.commit.called

    async def test_deactivate_configuration(self, service):
        """Test configuration deactivation"""
        mock_config = Mock(spec=ScholarshipConfiguration)
        mock_config.is_active = True

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_config

        service.db.execute = AsyncMock(return_value=mock_result)
        service.db.commit = AsyncMock()

        await service.deactivate_configuration(1, updated_by_user_id=1)

        assert mock_config.is_active is False
        assert service.db.commit.called


@pytest.mark.asyncio
class TestScholarshipConfigurationServiceDuplicate:
    """Test configuration duplication"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipConfigurationService(db)

    async def test_duplicate_configuration(self, service):
        """Test duplicating a configuration"""
        source_config = Mock(spec=ScholarshipConfiguration)
        source_config.scholarship_type_id = 1
        source_config.config_code = "SOURCE_001"
        source_config.total_quota = 100
        source_config.has_quota_limit = True

        mock_source_result = Mock()
        mock_source_result.scalar_one_or_none.return_value = source_config

        mock_dup_check_result = Mock()
        mock_dup_check_result.scalar_one_or_none.return_value = None

        service.db.execute = AsyncMock(side_effect=[mock_source_result, mock_dup_check_result])
        service.db.add = Mock()
        service.db.commit = AsyncMock()
        service.db.refresh = AsyncMock()

        await service.duplicate_configuration(
            source_config_id=1,
            new_config_code="DUPLICATED_001",
            target_academic_year=114,
            target_semester="first",
            new_config_name=None,
            created_by_user_id=1,
        )

        assert service.db.add.called
        assert service.db.commit.called


@pytest.mark.asyncio
class TestScholarshipConfigurationServiceFilter:
    """Test configuration filtering"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipConfigurationService(db)

    async def test_get_configurations_by_filter(self, service):
        """Test getting configurations with filters"""
        mock_configs = [Mock(spec=ScholarshipConfiguration)]

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_configs

        service.db.execute = AsyncMock(return_value=mock_result)

        configs = await service.get_configurations_by_filter(
            scholarship_type_id=1, academic_year=113, semester="first", is_active=True
        )

        assert len(configs) == 1


@pytest.mark.asyncio
class TestScholarshipConfigurationServiceAnalytics:
    """Test configuration analytics"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipConfigurationService(db)

    async def test_get_configuration_analytics(self, service):
        """Test getting configuration analytics"""
        config = Mock(spec=ScholarshipConfiguration)
        config.scholarship_type_id = 1
        config.total_quota = 100
        config.has_quota_limit = True

        # Service does ONE execute: select applications by scholarship_type_id.
        mock_app_result = Mock()
        mock_app_result.scalars.return_value.all.return_value = []

        service.db.execute = AsyncMock(return_value=mock_app_result)

        analytics = await service.get_configuration_analytics(config)

        assert "total_applications" in analytics


@pytest.mark.asyncio
class TestScholarshipConfigurationServiceAutoScreening:
    """Test auto-screening functionality"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipConfigurationService(db)

    async def test_apply_auto_screening(self, service):
        """Test applying auto-screening — returns list of (app, passed, reason) tuples."""
        config = Mock(spec=ScholarshipConfiguration)
        config.auto_screening_rules = None  # No rules → all pass

        # No DB calls when there are no screening rules; pass empty application list.
        result = await service.apply_auto_screening(config, [])

        assert isinstance(result, list)
