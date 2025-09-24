"""
Unit tests for ScholarshipConfigurationService CRUD operations
"""

from datetime import datetime

import pytest

from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole
from app.services.scholarship_configuration_service import (
    ScholarshipConfigurationService,
)


class TestScholarshipConfigurationServiceCRUD:
    """Test cases for ScholarshipConfiguration CRUD operations"""

    @pytest.fixture
    def service(self, db_sync):
        """Create ScholarshipConfigurationService instance for testing"""
        return ScholarshipConfigurationService(db_sync)

    @pytest.fixture
    def test_scholarship_type(self, db_sync):
        """Create a test scholarship type"""
        scholarship_type = ScholarshipType(
            code="test_phd",
            name="Test PhD Scholarship",
            description="Test PhD scholarship for configuration testing",
            category="doctoral",
            status="active",
        )
        db_sync.add(scholarship_type)
        db_sync.commit()
        db_sync.refresh(scholarship_type)
        return scholarship_type

    @pytest.fixture
    def test_user(self, db_sync):
        """Create a test user"""
        user = User(
            email="admin@university.edu",
            username="admin",
            full_name="Test Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db_sync.add(user)
        db_sync.commit()
        db_sync.refresh(user)
        return user

    @pytest.fixture
    def valid_config_data(self, test_scholarship_type):
        """Valid configuration data for testing"""
        return {
            "config_name": "113學年度第一學期博士生配置",
            "config_code": "PHD-113-1",
            "academic_year": 113,
            "semester": "first",
            "description": "Test configuration description",
            "description_en": "Test configuration description in English",
            "amount": 50000,
            "currency": "TWD",
            "application_start_date": datetime(2024, 9, 1, 9, 0),
            "application_end_date": datetime(2024, 10, 15, 23, 59),
            "effective_start_date": datetime(2024, 9, 1),
            "effective_end_date": datetime(2025, 6, 30),
            "requires_professor_recommendation": True,
            "requires_college_review": False,
            "is_active": True,
            "version": "1.0",
        }

    def test_create_configuration_success(
        self, service, test_scholarship_type, test_user, valid_config_data
    ):
        """Test successful configuration creation"""
        config = service.create_configuration(
            scholarship_type_id=test_scholarship_type.id,
            config_data=valid_config_data,
            created_by_user_id=test_user.id,
        )

        assert config is not None
        assert config.id is not None
        assert config.scholarship_type_id == test_scholarship_type.id
        assert config.config_name == valid_config_data["config_name"]
        assert config.config_code == valid_config_data["config_code"]
        assert config.academic_year == valid_config_data["academic_year"]
        assert config.semester == valid_config_data["semester"]
        assert config.amount == valid_config_data["amount"]
        assert config.is_active is True
        assert config.created_by == test_user.id

    def test_create_configuration_duplicate_fails(
        self, service, test_scholarship_type, test_user, valid_config_data
    ):
        """Test that creating duplicate configuration fails"""
        # Create first configuration
        service.create_configuration(
            scholarship_type_id=test_scholarship_type.id,
            config_data=valid_config_data,
            created_by_user_id=test_user.id,
        )

        # Attempt to create duplicate should fail
        with pytest.raises(
            ValueError, match="Configuration already exists for this academic period"
        ):
            service.create_configuration(
                scholarship_type_id=test_scholarship_type.id,
                config_data=valid_config_data,
                created_by_user_id=test_user.id,
            )

    def test_create_configuration_missing_required_fields(
        self, service, test_scholarship_type, test_user
    ):
        """Test that missing required fields causes failure"""
        invalid_data = {"description": "Missing required fields"}

        with pytest.raises(KeyError):
            service.create_configuration(
                scholarship_type_id=test_scholarship_type.id,
                config_data=invalid_data,
                created_by_user_id=test_user.id,
            )

    def test_update_configuration_success(
        self, service, test_scholarship_type, test_user, valid_config_data
    ):
        """Test successful configuration update"""
        # Create initial configuration
        config = service.create_configuration(
            scholarship_type_id=test_scholarship_type.id,
            config_data=valid_config_data,
            created_by_user_id=test_user.id,
        )

        # Update configuration
        update_data = {
            "config_name": "Updated Configuration Name",
            "amount": 60000,
            "description": "Updated description",
        }

        updated_config = service.update_configuration(
            config_id=config.id,
            config_data=update_data,
            updated_by_user_id=test_user.id,
        )

        assert updated_config.config_name == "Updated Configuration Name"
        assert updated_config.amount == 60000
        assert updated_config.description == "Updated description"
        assert updated_config.updated_by == test_user.id

    def test_update_nonexistent_configuration_fails(self, service, test_user):
        """Test that updating non-existent configuration fails"""
        with pytest.raises(ValueError, match="Configuration not found"):
            service.update_configuration(
                config_id=999,
                config_data={"config_name": "New Name"},
                updated_by_user_id=test_user.id,
            )

    def test_deactivate_configuration_success(
        self, service, test_scholarship_type, test_user, valid_config_data
    ):
        """Test successful configuration deactivation"""
        # Create configuration
        config = service.create_configuration(
            scholarship_type_id=test_scholarship_type.id,
            config_data=valid_config_data,
            created_by_user_id=test_user.id,
        )

        assert config.is_active is True

        # Deactivate configuration
        deactivated_config = service.deactivate_configuration(
            config_id=config.id, updated_by_user_id=test_user.id
        )

        assert deactivated_config.is_active is False
        assert deactivated_config.updated_by == test_user.id

    def test_deactivate_nonexistent_configuration_fails(self, service, test_user):
        """Test that deactivating non-existent configuration fails"""
        with pytest.raises(ValueError, match="Configuration not found"):
            service.deactivate_configuration(
                config_id=999, updated_by_user_id=test_user.id
            )

    def test_duplicate_configuration_success(
        self, service, test_scholarship_type, test_user, valid_config_data
    ):
        """Test successful configuration duplication"""
        # Create source configuration
        source_config = service.create_configuration(
            scholarship_type_id=test_scholarship_type.id,
            config_data=valid_config_data,
            created_by_user_id=test_user.id,
        )

        # Duplicate to next academic year
        duplicate_config = service.duplicate_configuration(
            source_config_id=source_config.id,
            target_academic_year=114,
            target_semester="first",
            new_config_code="PHD-114-1",
            new_config_name="114學年度第一學期博士生配置",
            created_by_user_id=test_user.id,
        )

        assert duplicate_config.id != source_config.id
        assert duplicate_config.academic_year == 114
        assert duplicate_config.semester == "first"
        assert duplicate_config.config_code == "PHD-114-1"
        assert duplicate_config.config_name == "114學年度第一學期博士生配置"
        assert duplicate_config.amount == source_config.amount  # Should copy amount
        assert (
            duplicate_config.description == source_config.description
        )  # Should copy description
        assert duplicate_config.created_by == test_user.id

    def test_duplicate_to_existing_period_fails(
        self, service, test_scholarship_type, test_user, valid_config_data
    ):
        """Test that duplicating to existing period fails"""
        # Create source configuration
        source_config = service.create_configuration(
            scholarship_type_id=test_scholarship_type.id,
            config_data=valid_config_data,
            created_by_user_id=test_user.id,
        )

        # Try to duplicate to same period should fail
        with pytest.raises(
            ValueError,
            match="Target configuration already exists for this academic period",
        ):
            service.duplicate_configuration(
                source_config_id=source_config.id,
                target_academic_year=113,
                target_semester="first",
                new_config_code="PHD-113-1-DUPLICATE",
                new_config_name="Duplicate Config",
                created_by_user_id=test_user.id,
            )

    def test_duplicate_nonexistent_source_fails(self, service, test_user):
        """Test that duplicating non-existent source fails"""
        with pytest.raises(ValueError, match="Source configuration not found"):
            service.duplicate_configuration(
                source_config_id=999,
                target_academic_year=114,
                target_semester="first",
                new_config_code="PHD-114-1",
                new_config_name="New Config",
                created_by_user_id=test_user.id,
            )

    def test_get_configurations_by_filter(
        self, service, test_scholarship_type, test_user, valid_config_data
    ):
        """Test filtering configurations"""
        # Create multiple configurations
        config1 = service.create_configuration(
            scholarship_type_id=test_scholarship_type.id,
            config_data=valid_config_data,
            created_by_user_id=test_user.id,
        )

        config2_data = valid_config_data.copy()
        config2_data.update({"config_code": "PHD-113-2", "semester": "second"})
        config2 = service.create_configuration(
            scholarship_type_id=test_scholarship_type.id,
            config_data=config2_data,
            created_by_user_id=test_user.id,
        )

        config3_data = valid_config_data.copy()
        config3_data.update({"config_code": "PHD-114-1", "academic_year": 114})
        config3 = service.create_configuration(
            scholarship_type_id=test_scholarship_type.id,
            config_data=config3_data,
            created_by_user_id=test_user.id,
        )

        # Test filtering by scholarship type
        configs = service.get_configurations_by_filter(
            scholarship_type_id=test_scholarship_type.id
        )
        assert len(configs) == 3

        # Test filtering by academic year
        configs = service.get_configurations_by_filter(
            scholarship_type_id=test_scholarship_type.id, academic_year=113
        )
        assert len(configs) == 2

        # Test filtering by semester
        configs = service.get_configurations_by_filter(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester="first",
        )
        assert len(configs) == 1
        assert configs[0].id == config1.id

    def test_validate_configuration_data_valid(self, service, valid_config_data):
        """Test validation of valid configuration data"""
        errors = service.validate_configuration_data(valid_config_data)
        assert len(errors) == 0

    def test_validate_configuration_data_missing_required(self, service):
        """Test validation with missing required fields"""
        invalid_data = {"description": "Missing required fields"}

        errors = service.validate_configuration_data(invalid_data)
        assert len(errors) > 0
        assert any("config_name is required" in error for error in errors)
        assert any("config_code is required" in error for error in errors)
        assert any("academic_year is required" in error for error in errors)
        assert any("amount is required" in error for error in errors)

    def test_validate_configuration_data_invalid_academic_year(self, service):
        """Test validation with invalid academic year"""
        invalid_data = {
            "config_name": "Test",
            "config_code": "TEST",
            "academic_year": 50,  # Too low
            "amount": 10000,
        }

        errors = service.validate_configuration_data(invalid_data)
        assert any(
            "Academic year should be in Taiwan calendar format" in error
            for error in errors
        )

    def test_validate_configuration_data_invalid_amount(self, service):
        """Test validation with invalid amount"""
        invalid_data = {
            "config_name": "Test",
            "config_code": "TEST",
            "academic_year": 113,
            "amount": -1000,  # Negative amount
        }

        errors = service.validate_configuration_data(invalid_data)
        assert any("Amount must be greater than 0" in error for error in errors)

    def test_validate_configuration_data_invalid_dates(self, service):
        """Test validation with invalid date ranges"""
        invalid_data = {
            "config_name": "Test",
            "config_code": "TEST",
            "academic_year": 113,
            "amount": 10000,
            "application_start_date": "2024-10-15T09:00:00",
            "application_end_date": "2024-10-01T23:59:59",  # End before start
        }

        errors = service.validate_configuration_data(invalid_data)
        assert any(
            "application_end_date must be after application_start_date" in error
            for error in errors
        )


class TestScholarshipConfigurationServiceIntegration:
    """Integration tests for ScholarshipConfigurationService"""

    @pytest.fixture
    def service(self, db_sync):
        return ScholarshipConfigurationService(db_sync)

    def test_configuration_lifecycle(self, service, db_sync):
        """Test complete configuration lifecycle"""
        # Create scholarship type
        scholarship_type = ScholarshipType(
            code="lifecycle_test",
            name="Lifecycle Test Scholarship",
            category="undergraduate",
            is_active=True,
        )
        db_sync.add(scholarship_type)
        db_sync.commit()
        db_sync.refresh(scholarship_type)

        # Create user
        user = User(
            email="lifecycle@test.edu",
            username="lifecycle",
            full_name="Lifecycle User",
            role=UserRole.ADMIN,
        )
        db_sync.add(user)
        db_sync.commit()
        db_sync.refresh(user)

        # Create configuration
        config_data = {
            "config_name": "Lifecycle Test Config",
            "config_code": "LIFECYCLE-113-1",
            "academic_year": 113,
            "semester": "first",
            "amount": 25000,
            "currency": "TWD",
        }

        config = service.create_configuration(
            scholarship_type_id=scholarship_type.id,
            config_data=config_data,
            created_by_user_id=user.id,
        )

        # Update configuration
        updated_config = service.update_configuration(
            config_id=config.id,
            config_data={"amount": 30000, "description": "Updated description"},
            updated_by_user_id=user.id,
        )

        # Duplicate configuration
        duplicate_config = service.duplicate_configuration(
            source_config_id=config.id,
            target_academic_year=114,
            target_semester="first",
            new_config_code="LIFECYCLE-114-1",
            new_config_name="Lifecycle Test Config (複製)",
            created_by_user_id=user.id,
        )

        # Deactivate original configuration
        deactivated_config = service.deactivate_configuration(
            config_id=config.id, updated_by_user_id=user.id
        )

        # Verify final states
        assert updated_config.amount == 30000
        assert duplicate_config.academic_year == 114
        assert deactivated_config.is_active is False

        # Verify filtering
        active_configs = service.get_configurations_by_filter(
            scholarship_type_id=scholarship_type.id, is_active=True
        )
        assert len(active_configs) == 1
        assert active_configs[0].id == duplicate_config.id
