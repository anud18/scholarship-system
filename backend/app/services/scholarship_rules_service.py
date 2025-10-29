"""
Scholarship Rules Service
Handles business logic for scholarship eligibility rules management
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import Semester
from app.models.scholarship import ScholarshipRule, ScholarshipType
from app.schemas.scholarship import ScholarshipRuleCreate, ScholarshipRuleUpdate

logger = logging.getLogger(__name__)


class ScholarshipRulesService:
    """Service for managing scholarship rules"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_rule(self, rule_data: ScholarshipRuleCreate, created_by: int) -> ScholarshipRule:
        """Create a new scholarship rule"""

        # Validate scholarship type exists
        await self._validate_scholarship_type(rule_data.scholarship_type_id)

        # Validate sub_type if provided
        if rule_data.sub_type:
            await self._validate_sub_type(rule_data.scholarship_type_id, rule_data.sub_type)

        # Create rule
        rule = ScholarshipRule(**rule_data.model_dump(), created_by=created_by, updated_by=created_by)

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)

        return rule

    async def update_rule(self, rule_id: int, rule_update: ScholarshipRuleUpdate, updated_by: int) -> ScholarshipRule:
        """Update an existing scholarship rule"""

        # Get existing rule
        rule = await self._get_rule_by_id(rule_id)

        # Validate sub_type if being updated
        if rule_update.sub_type:
            await self._validate_sub_type(rule.scholarship_type_id, rule_update.sub_type)

        # Update only fields defined in the Pydantic schema to prevent mass assignment
        # This automatically stays in sync with schema changes
        allowed_fields = set(rule_update.model_fields.keys())

        update_data = rule_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field in allowed_fields and hasattr(rule, field):
                setattr(rule, field, value)

        rule.updated_by = updated_by

        await self.db.commit()
        await self.db.refresh(rule)

        return rule

    async def delete_rule(self, rule_id: int) -> bool:
        """Delete a scholarship rule"""

        rule = await self._get_rule_by_id(rule_id)
        await self.db.delete(rule)
        await self.db.commit()

        return True

    async def get_rules_by_filters(
        self,
        scholarship_type_id: Optional[int] = None,
        academic_year: Optional[int] = None,
        semester: Optional[Semester] = None,
        sub_type: Optional[str] = None,
        rule_type: Optional[str] = None,
        is_template: Optional[bool] = None,
        is_active: Optional[bool] = None,
        tag: Optional[str] = None,
        include_generic: bool = True,
    ) -> List[ScholarshipRule]:
        """Get rules with various filters"""

        stmt = select(ScholarshipRule).options(
            selectinload(ScholarshipRule.scholarship_type),
            selectinload(ScholarshipRule.creator),
            selectinload(ScholarshipRule.updater),
        )

        # Apply filters
        if scholarship_type_id:
            stmt = stmt.filter(ScholarshipRule.scholarship_type_id == scholarship_type_id)

        if academic_year:
            if include_generic:
                stmt = stmt.filter(
                    or_(
                        ScholarshipRule.academic_year == academic_year,
                        ScholarshipRule.academic_year.is_(None),
                    )
                )
            else:
                stmt = stmt.filter(ScholarshipRule.academic_year == academic_year)

        if semester:
            if include_generic:
                stmt = stmt.filter(
                    or_(
                        ScholarshipRule.semester == semester,
                        ScholarshipRule.semester.is_(None),
                    )
                )
            else:
                stmt = stmt.filter(ScholarshipRule.semester == semester)

        if sub_type:
            if include_generic:
                stmt = stmt.filter(
                    or_(
                        ScholarshipRule.sub_type == sub_type,
                        ScholarshipRule.sub_type.is_(None),
                    )
                )
            else:
                stmt = stmt.filter(ScholarshipRule.sub_type == sub_type)

        if rule_type:
            stmt = stmt.filter(ScholarshipRule.rule_type == rule_type)

        if is_template is not None:
            stmt = stmt.filter(ScholarshipRule.is_template == is_template)

        if is_active is not None:
            stmt = stmt.filter(ScholarshipRule.is_active == is_active)

        if tag:
            stmt = stmt.filter(ScholarshipRule.tag.ilike(f"%{tag}%"))

        # Order by priority then created_at
        stmt = stmt.order_by(desc(ScholarshipRule.priority), desc(ScholarshipRule.created_at))

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def copy_rules_to_period(
        self,
        source_academic_year: Optional[int],
        source_semester: Optional[Semester],
        target_academic_year: int,
        target_semester: Optional[Semester],
        scholarship_type_ids: Optional[List[int]] = None,
        rule_ids: Optional[List[int]] = None,
        overwrite_existing: bool = False,
        created_by: int = None,
    ) -> Tuple[int, int]:  # (copied_count, skipped_count)
        """Copy rules from one period to another"""

        # Build source query
        source_stmt = select(ScholarshipRule).filter(ScholarshipRule.is_template.is_(False))

        if source_academic_year:
            source_stmt = source_stmt.filter(ScholarshipRule.academic_year == source_academic_year)

        if source_semester:
            source_stmt = source_stmt.filter(ScholarshipRule.semester == source_semester)

        if scholarship_type_ids:
            source_stmt = source_stmt.filter(ScholarshipRule.scholarship_type_id.in_(scholarship_type_ids))

        if rule_ids:
            source_stmt = source_stmt.filter(ScholarshipRule.id.in_(rule_ids))

        # Get source rules
        source_result = await self.db.execute(source_stmt)
        source_rules = source_result.scalars().all()

        copied_count = 0
        skipped_count = 0

        for source_rule in source_rules:
            # Check if target rule already exists
            existing_rule = await self._find_existing_rule(
                source_rule.scholarship_type_id,
                target_academic_year,
                target_semester,
                source_rule.rule_name,
                source_rule.rule_type,
                source_rule.sub_type,
            )

            if existing_rule and not overwrite_existing:
                skipped_count += 1
                continue

            if existing_rule and overwrite_existing:
                # Update existing rule
                await self._update_rule_from_source(existing_rule, source_rule, created_by)
                copied_count += 1
            else:
                # Create new rule
                await self._create_rule_from_source(source_rule, target_academic_year, target_semester, created_by)
                copied_count += 1

        await self.db.commit()
        return copied_count, skipped_count

    async def create_template_from_rules(
        self,
        template_name: str,
        template_description: Optional[str],
        scholarship_type_id: int,
        rule_ids: List[int],
        created_by: int,
    ) -> List[ScholarshipRule]:
        """Create template rules from existing rules"""

        # Get source rules
        stmt = select(ScholarshipRule).filter(ScholarshipRule.id.in_(rule_ids))
        result = await self.db.execute(stmt)
        source_rules = result.scalars().all()

        if len(source_rules) != len(rule_ids):
            raise ValueError("Some rules not found")

        template_rules = []

        for source_rule in source_rules:
            template_rule = ScholarshipRule(
                scholarship_type_id=scholarship_type_id,
                sub_type=source_rule.sub_type,
                academic_year=None,  # Templates are not period-specific
                semester=None,
                is_template=True,
                template_name=template_name,
                template_description=template_description,
                rule_name=source_rule.rule_name,
                rule_type=source_rule.rule_type,
                tag=source_rule.tag,
                description=source_rule.description,
                condition_field=source_rule.condition_field,
                operator=source_rule.operator,
                expected_value=source_rule.expected_value,
                message=source_rule.message,
                message_en=source_rule.message_en,
                is_hard_rule=source_rule.is_hard_rule,
                is_warning=source_rule.is_warning,
                priority=source_rule.priority,
                is_active=source_rule.is_active,
                is_initial_enabled=source_rule.is_initial_enabled,
                is_renewal_enabled=source_rule.is_renewal_enabled,
                created_by=created_by,
                updated_by=created_by,
            )

            self.db.add(template_rule)
            template_rules.append(template_rule)

        await self.db.commit()
        return template_rules

    async def apply_template(
        self,
        template_id: int,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[Semester],
        overwrite_existing: bool = False,
        created_by: int = None,
    ) -> int:  # Returns count of applied rules
        """Apply a template to a specific period"""

        # Get template rule
        template_rule = await self._get_rule_by_id(template_id)

        if not template_rule.is_template:
            raise ValueError("Rule is not a template")

        # Get all rules with the same template name
        stmt = select(ScholarshipRule).filter(
            and_(
                ScholarshipRule.is_template.is_(True),
                ScholarshipRule.template_name == template_rule.template_name,
                ScholarshipRule.scholarship_type_id == template_rule.scholarship_type_id,
            )
        )

        result = await self.db.execute(stmt)
        template_rules = result.scalars().all()

        applied_count = 0

        for template_rule in template_rules:
            # Check if rule already exists in target period
            existing_rule = await self._find_existing_rule(
                scholarship_type_id,
                academic_year,
                semester,
                template_rule.rule_name,
                template_rule.rule_type,
                template_rule.sub_type,
            )

            if existing_rule and not overwrite_existing:
                continue

            if existing_rule and overwrite_existing:
                # Update existing rule
                await self._update_rule_from_source(existing_rule, template_rule, created_by)
                applied_count += 1
            else:
                # Create new rule
                await self._create_rule_from_source(
                    template_rule,
                    academic_year,
                    semester,
                    created_by,
                    target_scholarship_type_id=scholarship_type_id,
                )
                applied_count += 1

        await self.db.commit()
        return applied_count

    async def validate_rule_condition(
        self,
        condition_field: str,
        operator: str,
        expected_value: str,
        test_data: Dict[str, Any] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validate rule condition syntax and optionally test with sample data"""

        # Validate operator
        valid_operators = [
            ">=",
            "<=",
            "==",
            "!=",
            ">",
            "<",
            "in",
            "not_in",
            "contains",
            "not_contains",
        ]
        if operator not in valid_operators:
            return (
                False,
                f"Invalid operator: {operator}. Valid operators: {', '.join(valid_operators)}",
            )

        # Validate expected_value format for list-based operators
        if operator in ["in", "not_in"]:
            try:
                # Test if it can be split into valid list
                values = [v.strip() for v in expected_value.split(",")]
                if not values or any(not v for v in values):
                    return (
                        False,
                        f"For '{operator}' operator, expected_value must be comma-separated non-empty values",
                    )
            except Exception:
                return False, f"Invalid expected_value format for '{operator}' operator"

        # Test with sample data if provided
        if test_data:
            try:
                field_value = self._get_nested_field_value(test_data, condition_field)
                result = self._evaluate_rule_condition(field_value, operator, expected_value)
                return (
                    True,
                    f"Test passed: field_value='{field_value}' {operator} '{expected_value}' = {result}",
                )
            except Exception as e:
                return False, f"Test failed: {str(e)}"

        return True, "Condition syntax is valid"

    # Private helper methods

    async def _validate_scholarship_type(self, scholarship_type_id: int):
        """Validate that scholarship type exists"""
        stmt = select(ScholarshipType).filter(ScholarshipType.id == scholarship_type_id)
        result = await self.db.execute(stmt)
        scholarship_type = result.scalar_one_or_none()

        if not scholarship_type:
            raise ValueError(f"Scholarship type {scholarship_type_id} not found")

        return scholarship_type

    async def _validate_sub_type(self, scholarship_type_id: int, sub_type: str):
        """Validate that sub_type is valid for the scholarship type"""
        scholarship_type = await self._validate_scholarship_type(scholarship_type_id)

        if not scholarship_type.sub_type_list or sub_type not in scholarship_type.sub_type_list:
            raise ValueError(f"Sub-type '{sub_type}' is not valid for scholarship type '{scholarship_type.name}'")

    async def _get_rule_by_id(self, rule_id: int) -> ScholarshipRule:
        """Get rule by ID with error handling"""
        stmt = select(ScholarshipRule).filter(ScholarshipRule.id == rule_id)
        result = await self.db.execute(stmt)
        rule = result.scalar_one_or_none()

        if not rule:
            raise ValueError(f"Rule {rule_id} not found")

        return rule

    async def _find_existing_rule(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[Semester],
        rule_name: str,
        rule_type: str,
        sub_type: Optional[str],
    ) -> Optional[ScholarshipRule]:
        """Find existing rule with same characteristics"""
        stmt = select(ScholarshipRule).filter(
            and_(
                ScholarshipRule.scholarship_type_id == scholarship_type_id,
                ScholarshipRule.academic_year == academic_year,
                ScholarshipRule.semester == semester,
                ScholarshipRule.rule_name == rule_name,
                ScholarshipRule.rule_type == rule_type,
                ScholarshipRule.sub_type == sub_type,
            )
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _update_rule_from_source(
        self,
        target_rule: ScholarshipRule,
        source_rule: ScholarshipRule,
        updated_by: int,
    ):
        """Update existing rule with data from source rule"""
        fields_to_copy = [
            "condition_field",
            "operator",
            "expected_value",
            "message",
            "message_en",
            "is_hard_rule",
            "is_warning",
            "priority",
            "description",
            "tag",
            "is_initial_enabled",
            "is_renewal_enabled",
        ]

        for field in fields_to_copy:
            setattr(target_rule, field, getattr(source_rule, field))

        target_rule.updated_by = updated_by

    async def _create_rule_from_source(
        self,
        source_rule: ScholarshipRule,
        target_academic_year: int,
        target_semester: Optional[Semester],
        created_by: int,
        target_scholarship_type_id: Optional[int] = None,
    ):
        """Create new rule from source rule"""
        new_rule = ScholarshipRule(
            scholarship_type_id=target_scholarship_type_id or source_rule.scholarship_type_id,
            sub_type=source_rule.sub_type,
            academic_year=target_academic_year,
            semester=target_semester,
            is_template=False,  # Copied rules are not templates
            template_name=None,
            template_description=None,
            rule_name=source_rule.rule_name,
            rule_type=source_rule.rule_type,
            tag=source_rule.tag,
            description=source_rule.description,
            condition_field=source_rule.condition_field,
            operator=source_rule.operator,
            expected_value=source_rule.expected_value,
            message=source_rule.message,
            message_en=source_rule.message_en,
            is_hard_rule=source_rule.is_hard_rule,
            is_warning=source_rule.is_warning,
            priority=source_rule.priority,
            is_active=source_rule.is_active,
            is_initial_enabled=source_rule.is_initial_enabled,
            is_renewal_enabled=source_rule.is_renewal_enabled,
            created_by=created_by,
            updated_by=created_by,
        )

        self.db.add(new_rule)

    def _get_nested_field_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Get value from nested dictionary using dot notation"""
        if "." not in field_path:
            return data.get(field_path, "")

        parts = field_path.split(".")
        current_data = data

        for part in parts:
            if isinstance(current_data, dict):
                current_data = current_data.get(part, "")
            else:
                return ""

        return current_data

    def _evaluate_rule_condition(self, field_value: Any, operator: str, expected_value: str) -> bool:
        """Evaluate rule condition - same logic as in EligibilityService"""
        try:
            if operator == ">=":
                return float(field_value) >= float(expected_value)
            elif operator == "<=":
                return float(field_value) <= float(expected_value)
            elif operator == ">":
                return float(field_value) > float(expected_value)
            elif operator == "<":
                return float(field_value) < float(expected_value)
            elif operator == "==":
                return str(field_value) == str(expected_value)
            elif operator == "!=":
                return str(field_value) != str(expected_value)
            elif operator == "in":
                allowed_values = [v.strip() for v in expected_value.split(",")]
                return str(field_value) in allowed_values
            elif operator == "not_in":
                forbidden_values = [v.strip() for v in expected_value.split(",")]
                return str(field_value) not in forbidden_values
            elif operator == "contains":
                return expected_value in str(field_value)
            elif operator == "not_contains":
                return expected_value not in str(field_value)
            else:
                return False
        except (ValueError, TypeError):
            return False
