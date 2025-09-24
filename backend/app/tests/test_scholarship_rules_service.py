"""
Comprehensive tests for ScholarshipRulesService
Target: 0% → 80% coverage
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Semester
from app.models.scholarship import ScholarshipRule, ScholarshipType
from app.schemas.scholarship import ScholarshipRuleCreate, ScholarshipRuleUpdate
from app.services.scholarship_rules_service import ScholarshipRulesService


@pytest.mark.asyncio
class TestScholarshipRulesServiceCreate:
    """Test rule creation"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipRulesService(db)

    @pytest.fixture
    def mock_scholarship_type(self):
        return Mock(
            spec=ScholarshipType,
            id=1,
            name="Test Scholarship",
            sub_type_list=["type_a", "type_b"],
        )

    async def test_create_rule_success(self, service, mock_scholarship_type):
        """Test successful rule creation"""
        rule_data = ScholarshipRuleCreate(
            scholarship_type_id=1,
            academic_year=113,
            semester=Semester.FIRST,
            rule_name="GPA Check",
            rule_type="academic",
            condition_field="std_gpa",
            operator=">=",
            expected_value="3.0",
            message="GPA must be 3.0 or higher",
            is_hard_rule=True,
        )

        with patch.object(
            service, "_validate_scholarship_type", return_value=mock_scholarship_type
        ), patch.object(service.db, "add"), patch.object(
            service.db, "commit", new_callable=AsyncMock
        ), patch.object(
            service.db, "refresh", new_callable=AsyncMock
        ):
            result = await service.create_rule(rule_data, created_by=1)

            service.db.add.assert_called_once()
            assert service.db.commit.called
            assert service.db.refresh.called

    async def test_create_rule_with_sub_type(self, service, mock_scholarship_type):
        """Test rule creation with sub_type validation"""
        rule_data = ScholarshipRuleCreate(
            scholarship_type_id=1,
            sub_type="type_a",
            academic_year=113,
            semester=Semester.FIRST,
            rule_name="Test Rule",
            rule_type="academic",
            condition_field="std_gpa",
            operator=">=",
            expected_value="3.0",
            message="Test message",
            is_hard_rule=True,
        )

        with patch.object(
            service, "_validate_scholarship_type", return_value=mock_scholarship_type
        ), patch.object(
            service, "_validate_sub_type", new_callable=AsyncMock
        ), patch.object(
            service.db, "add"
        ), patch.object(
            service.db, "commit", new_callable=AsyncMock
        ), patch.object(
            service.db, "refresh", new_callable=AsyncMock
        ):
            await service.create_rule(rule_data, created_by=1)

            service._validate_sub_type.assert_called_once_with(1, "type_a")


@pytest.mark.asyncio
class TestScholarshipRulesServiceUpdate:
    """Test rule updates"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipRulesService(db)

    @pytest.fixture
    def existing_rule(self):
        return Mock(
            spec=ScholarshipRule,
            id=1,
            scholarship_type_id=1,
            rule_name="GPA Check",
            operator=">=",
            expected_value="3.0",
            is_hard_rule=True,
        )

    async def test_update_rule_success(self, service, existing_rule):
        """Test successful rule update"""
        rule_update = ScholarshipRuleUpdate(
            rule_name="GPA Check",
            rule_type="academic",
            condition_field="std_gpa",
            operator=">=",
            expected_value="3.5",
            message="Updated message",
        )

        with patch.object(
            service, "_get_rule_by_id", return_value=existing_rule
        ), patch.object(service.db, "commit", new_callable=AsyncMock), patch.object(
            service.db, "refresh", new_callable=AsyncMock
        ):
            result = await service.update_rule(1, rule_update, updated_by=2)

            assert existing_rule.expected_value == "3.5"
            assert existing_rule.message == "Updated message"
            assert existing_rule.updated_by == 2

    async def test_update_rule_with_sub_type(self, service, existing_rule):
        """Test rule update with sub_type validation"""
        rule_update = ScholarshipRuleUpdate(
            rule_name="GPA Check",
            rule_type="academic",
            condition_field="std_gpa",
            operator=">=",
            expected_value="3.0",
            sub_type="type_b",
        )

        with patch.object(
            service, "_get_rule_by_id", return_value=existing_rule
        ), patch.object(
            service, "_validate_sub_type", new_callable=AsyncMock
        ), patch.object(
            service.db, "commit", new_callable=AsyncMock
        ), patch.object(
            service.db, "refresh", new_callable=AsyncMock
        ):
            await service.update_rule(1, rule_update, updated_by=2)

            service._validate_sub_type.assert_called_once()


@pytest.mark.asyncio
class TestScholarshipRulesServiceDelete:
    """Test rule deletion"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipRulesService(db)

    async def test_delete_rule_success(self, service):
        """Test successful rule deletion"""
        rule = Mock(spec=ScholarshipRule, id=1)

        with patch.object(service, "_get_rule_by_id", return_value=rule), patch.object(
            service.db, "delete", new_callable=AsyncMock
        ), patch.object(service.db, "commit", new_callable=AsyncMock):
            result = await service.delete_rule(1)

            assert result == True
            service.db.delete.assert_called_once_with(rule)
            assert service.db.commit.called


@pytest.mark.asyncio
class TestScholarshipRulesServiceFilters:
    """Test filtering rules"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipRulesService(db)

    async def test_get_rules_basic_filters(self, service):
        """Test basic filter application"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        service.db.execute = AsyncMock(return_value=mock_result)

        rules = await service.get_rules_by_filters(
            scholarship_type_id=1,
            academic_year=113,
            semester=Semester.FIRST,
            is_active=True,
        )

        assert rules == []
        assert service.db.execute.called

    async def test_get_rules_with_tag_filter(self, service):
        """Test tag filtering"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        service.db.execute = AsyncMock(return_value=mock_result)

        rules = await service.get_rules_by_filters(tag="academic")

        assert rules == []
        assert service.db.execute.called

    async def test_get_rules_include_generic(self, service):
        """Test include_generic flag"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        service.db.execute = AsyncMock(return_value=mock_result)

        rules = await service.get_rules_by_filters(
            academic_year=113, include_generic=True
        )

        assert rules == []


@pytest.mark.asyncio
class TestScholarshipRulesServiceCopy:
    """Test rule copying"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipRulesService(db)

    @pytest.fixture
    def source_rules(self):
        return [
            Mock(
                spec=ScholarshipRule,
                scholarship_type_id=1,
                rule_name="GPA Check",
                rule_type="academic",
                sub_type=None,
                condition_field="std_gpa",
                operator=">=",
                expected_value="3.0",
                is_hard_rule=True,
            )
        ]

    async def test_copy_rules_to_period_success(self, service, source_rules):
        """Test successful rule copying"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = source_rules
        service.db.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            service, "_find_existing_rule", return_value=None
        ), patch.object(
            service, "_create_rule_from_source", new_callable=AsyncMock
        ), patch.object(
            service.db, "commit", new_callable=AsyncMock
        ):
            copied, skipped = await service.copy_rules_to_period(
                source_academic_year=112,
                source_semester=Semester.FIRST,
                target_academic_year=113,
                target_semester=Semester.FIRST,
                created_by=1,
            )

            assert copied == 1
            assert skipped == 0

    async def test_copy_rules_skip_existing(self, service, source_rules):
        """Test skipping existing rules"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = source_rules
        service.db.execute = AsyncMock(return_value=mock_result)

        existing_rule = Mock(spec=ScholarshipRule)

        with patch.object(
            service, "_find_existing_rule", return_value=existing_rule
        ), patch.object(service.db, "commit", new_callable=AsyncMock):
            copied, skipped = await service.copy_rules_to_period(
                source_academic_year=112,
                source_semester=Semester.FIRST,
                target_academic_year=113,
                target_semester=Semester.FIRST,
                overwrite_existing=False,
                created_by=1,
            )

            assert copied == 0
            assert skipped == 1

    async def test_copy_rules_overwrite_existing(self, service, source_rules):
        """Test overwriting existing rules"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = source_rules
        service.db.execute = AsyncMock(return_value=mock_result)

        existing_rule = Mock(spec=ScholarshipRule)

        with patch.object(
            service, "_find_existing_rule", return_value=existing_rule
        ), patch.object(
            service, "_update_rule_from_source", new_callable=AsyncMock
        ), patch.object(
            service.db, "commit", new_callable=AsyncMock
        ):
            copied, skipped = await service.copy_rules_to_period(
                source_academic_year=112,
                source_semester=Semester.FIRST,
                target_academic_year=113,
                target_semester=Semester.FIRST,
                overwrite_existing=True,
                created_by=1,
            )

            assert copied == 1
            assert skipped == 0


@pytest.mark.asyncio
class TestScholarshipRulesServiceTemplate:
    """Test template management"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipRulesService(db)

    @pytest.fixture
    def source_rules(self):
        return [
            Mock(
                spec=ScholarshipRule,
                id=1,
                rule_name="GPA Check",
                rule_type="academic",
                sub_type=None,
            )
        ]

    async def test_create_template_from_rules(self, service, source_rules):
        """Test creating template from rules"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = source_rules
        service.db.execute = AsyncMock(return_value=mock_result)

        with patch.object(service.db, "add"), patch.object(
            service.db, "commit", new_callable=AsyncMock
        ):
            templates = await service.create_template_from_rules(
                template_name="Academic Template",
                template_description="Standard academic rules",
                scholarship_type_id=1,
                rule_ids=[1],
                created_by=1,
            )

            assert len(templates) == 1
            assert service.db.add.called

    async def test_apply_template_success(self, service):
        """Test applying template to period"""
        template_rule = Mock(
            spec=ScholarshipRule,
            id=1,
            is_template=True,
            template_name="Academic Template",
            scholarship_type_id=1,
        )

        template_rules = [template_rule]
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = template_rules

        with patch.object(
            service, "_get_rule_by_id", return_value=template_rule
        ), patch.object(
            service.db, "execute", new_callable=AsyncMock, return_value=mock_result
        ), patch.object(
            service, "_find_existing_rule", return_value=None
        ), patch.object(
            service, "_create_rule_from_source", new_callable=AsyncMock
        ), patch.object(
            service.db, "commit", new_callable=AsyncMock
        ):
            count = await service.apply_template(
                template_id=1,
                scholarship_type_id=1,
                academic_year=113,
                semester=Semester.FIRST,
                created_by=1,
            )

            assert count == 1

    async def test_apply_non_template_fails(self, service):
        """Test applying non-template rule fails"""
        non_template = Mock(spec=ScholarshipRule, id=1, is_template=False)

        with patch.object(
            service, "_get_rule_by_id", return_value=non_template
        ), pytest.raises(ValueError, match="not a template"):
            await service.apply_template(
                template_id=1,
                scholarship_type_id=1,
                academic_year=113,
                semester=Semester.FIRST,
                created_by=1,
            )


@pytest.mark.asyncio
class TestScholarshipRulesServiceValidation:
    """Test rule validation"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipRulesService(db)

    async def test_validate_rule_condition_valid_operator(self, service):
        """Test validation with valid operator"""
        is_valid, message = await service.validate_rule_condition(
            condition_field="std_gpa", operator=">=", expected_value="3.0"
        )

        assert is_valid == True
        assert "valid" in message.lower()

    async def test_validate_rule_condition_invalid_operator(self, service):
        """Test validation with invalid operator"""
        is_valid, message = await service.validate_rule_condition(
            condition_field="std_gpa", operator="===", expected_value="3.0"
        )

        assert is_valid == False
        assert "invalid operator" in message.lower()

    async def test_validate_rule_condition_list_operator(self, service):
        """Test validation for list-based operators"""
        is_valid, message = await service.validate_rule_condition(
            condition_field="department", operator="in", expected_value="CS, EE, ME"
        )

        assert is_valid == True

    async def test_validate_rule_condition_with_test_data(self, service):
        """Test validation with test data"""
        test_data = {"std_gpa": 3.5}

        is_valid, message = await service.validate_rule_condition(
            condition_field="std_gpa",
            operator=">=",
            expected_value="3.0",
            test_data=test_data,
        )

        assert is_valid == True
        assert "test passed" in message.lower()


class TestScholarshipRulesServiceHelpers:
    """Test helper methods"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ScholarshipRulesService(db)

    def test_get_nested_field_value_simple(self, service):
        """Test getting simple field value"""
        data = {"std_gpa": 3.5}
        value = service._get_nested_field_value(data, "std_gpa")
        assert value == 3.5

    def test_get_nested_field_value_nested(self, service):
        """Test getting nested field value"""
        data = {"student": {"gpa": 3.5}}
        value = service._get_nested_field_value(data, "student.gpa")
        assert value == 3.5

    def test_get_nested_field_value_missing(self, service):
        """Test getting missing field value"""
        data = {"std_gpa": 3.5}
        value = service._get_nested_field_value(data, "missing_field")
        assert value == ""

    def test_evaluate_rule_condition_comparison(self, service):
        """Test comparison operators"""
        assert service._evaluate_rule_condition(3.5, ">=", "3.0") == True
        assert service._evaluate_rule_condition(3.5, "<=", "3.0") == False
        assert service._evaluate_rule_condition(3.5, ">", "3.0") == True
        assert service._evaluate_rule_condition(3.5, "<", "4.0") == True

    def test_evaluate_rule_condition_equality(self, service):
        """Test equality operators"""
        assert service._evaluate_rule_condition("CS", "==", "CS") == True
        assert service._evaluate_rule_condition("CS", "!=", "EE") == True

    def test_evaluate_rule_condition_list(self, service):
        """Test list operators"""
        assert service._evaluate_rule_condition("CS", "in", "CS, EE, ME") == True
        assert service._evaluate_rule_condition("CS", "not_in", "EE, ME") == True

    def test_evaluate_rule_condition_contains(self, service):
        """Test contains operators"""
        assert (
            service._evaluate_rule_condition("Computer Science", "contains", "Computer")
            == True
        )
        assert (
            service._evaluate_rule_condition("Computer Science", "not_contains", "Math")
            == True
        )

    def test_evaluate_rule_condition_invalid(self, service):
        """Test invalid condition handling"""
        assert service._evaluate_rule_condition("abc", ">=", "3.0") == False
        assert service._evaluate_rule_condition(None, "==", "test") == False
