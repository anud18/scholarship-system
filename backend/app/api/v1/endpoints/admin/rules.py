"""
Admin Scholarship Rules Management API Endpoints

Handles scholarship rule operations including:
- CRUD operations for rules
- Rule templates
- Bulk operations
- Cross-period rule copying
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.core.security import check_scholarship_permission, require_admin
from app.db.deps import get_db
from app.models.enums import Semester
from app.models.scholarship import ScholarshipRule, ScholarshipType
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.scholarship import (
    ApplyTemplateRequest,
    BulkRuleOperation,
    RuleCopyRequest,
    RuleTemplateRequest,
    ScholarshipRuleCreate,
    ScholarshipRuleResponse,
    ScholarshipRuleUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/scholarship-rules")
async def get_scholarship_rules(
    scholarship_type_id: Optional[int] = Query(None, description="Filter by scholarship type"),
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    sub_type: Optional[str] = Query(None, description="Filter by sub type"),
    rule_type: Optional[str] = Query(None, description="Filter by rule type"),
    is_template: Optional[bool] = Query(None, description="Filter templates"),
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get scholarship rules with optional filters"""

    # Check scholarship permission if specific scholarship type is requested
    if scholarship_type_id:
        check_scholarship_permission(current_user, scholarship_type_id)

    # Build query with joins
    stmt = select(ScholarshipRule).options(
        selectinload(ScholarshipRule.scholarship_type),
        selectinload(ScholarshipRule.creator),
        selectinload(ScholarshipRule.updater),
    )

    # Apply filters
    if scholarship_type_id:
        stmt = stmt.where(ScholarshipRule.scholarship_type_id == scholarship_type_id)
    elif not current_user.is_super_admin():
        # If no specific scholarship type requested and user is not super admin,
        # only show rules for scholarships they have permission to manage
        admin_scholarship_ids = [
            admin_scholarship.scholarship_id for admin_scholarship in current_user.admin_scholarships
        ]
        if admin_scholarship_ids:
            stmt = stmt.where(ScholarshipRule.scholarship_type_id.in_(admin_scholarship_ids))
        else:
            # Admin has no scholarship permissions, return empty result
            return {"success": True, "message": "No scholarship rules found", "data": []}

    if academic_year:
        stmt = stmt.where(ScholarshipRule.academic_year == academic_year)

    if semester:
        semester_enum = Semester.first if semester == "first" else Semester.second if semester == "second" else None
        if semester_enum:
            stmt = stmt.where(ScholarshipRule.semester == semester_enum)
        # If semester is provided but not recognized, don't filter by semester
    # Note: If semester parameter is not provided at all (for yearly scholarships),
    # the query will return rules with any semester value including NULL

    if sub_type:
        stmt = stmt.where(ScholarshipRule.sub_type == sub_type)

    if rule_type:
        stmt = stmt.where(ScholarshipRule.rule_type == rule_type)

    if is_template is not None:
        stmt = stmt.where(ScholarshipRule.is_template == is_template)

    if is_active is not None:
        stmt = stmt.where(ScholarshipRule.is_active == is_active)

    if tag:
        stmt = stmt.where(ScholarshipRule.tag.icontains(tag))

    # Log query parameters for debugging
    logger.info(
        f"[RULES] Querying scholarship rules - type_id={scholarship_type_id}, "
        f"year={academic_year}, semester={semester}, is_template={is_template}, "
        f"is_active={is_active}, sub_type={sub_type}, rule_type={rule_type}, tag={tag}"
    )

    # Order by priority and created date
    stmt = stmt.order_by(ScholarshipRule.priority.desc(), ScholarshipRule.created_at.desc())

    result = await db.execute(stmt)
    rules = result.scalars().all()

    logger.info(f"[RULES] Found {len(rules)} scholarship rules matching the criteria")

    # Convert to response format
    rule_responses = []
    for rule in rules:
        # Ensure all attributes are loaded in the session context
        await db.refresh(rule)

        rule_data = ScholarshipRuleResponse.model_validate(rule)
        rule_data.academic_period_label = rule.academic_period_label
        rule_responses.append(rule_data)

    return {"success": True, "message": f"Retrieved {len(rule_responses)} scholarship rules", "data": rule_responses}


@router.post("/scholarship-rules")
async def create_scholarship_rule(
    rule_data: ScholarshipRuleCreate, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Create a new scholarship rule"""

    # Check permission to manage this scholarship
    check_scholarship_permission(current_user, rule_data.scholarship_type_id)

    # Verify scholarship type exists
    stmt = select(ScholarshipType).where(ScholarshipType.id == rule_data.scholarship_type_id)
    result = await db.execute(stmt)
    scholarship_type = result.scalar_one_or_none()

    if not scholarship_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scholarship type not found")

    # Create new rule
    new_rule = ScholarshipRule(**rule_data.dict(), created_by=current_user.id, updated_by=current_user.id)

    db.add(new_rule)
    await db.commit()
    # Load relationships in a single query
    refreshed_rule_stmt = (
        select(ScholarshipRule)
        .options(
            selectinload(ScholarshipRule.scholarship_type),
            selectinload(ScholarshipRule.creator),
            selectinload(ScholarshipRule.updater),
        )
        .where(ScholarshipRule.id == new_rule.id)
    )

    refreshed_result = await db.execute(refreshed_rule_stmt)
    new_rule = refreshed_result.scalar_one()

    rule_response = ScholarshipRuleResponse.model_validate(new_rule)
    rule_response.academic_period_label = new_rule.academic_period_label

    return {"success": True, "message": "Scholarship rule created successfully", "data": rule_response}


@router.get("/scholarship-rules/{id}")
async def get_scholarship_rule(
    id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Get a specific scholarship rule"""

    stmt = (
        select(ScholarshipRule)
        .options(
            selectinload(ScholarshipRule.scholarship_type),
            selectinload(ScholarshipRule.creator),
            selectinload(ScholarshipRule.updater),
        )
        .where(ScholarshipRule.id == id)
    )

    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scholarship rule not found")

    # Check permission to manage this scholarship
    check_scholarship_permission(current_user, rule.scholarship_type_id)

    # Ensure all attributes are loaded in the session context
    await db.refresh(rule)

    rule_response = ScholarshipRuleResponse.model_validate(rule)
    rule_response.academic_period_label = rule.academic_period_label

    return {"success": True, "message": "Scholarship rule retrieved successfully", "data": rule_response}


@router.put("/scholarship-rules/{id}")
async def update_scholarship_rule(
    id: int,
    rule_data: ScholarshipRuleUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a scholarship rule"""

    # Get existing rule
    stmt = select(ScholarshipRule).where(ScholarshipRule.id == id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scholarship rule not found")

    # Check permission to manage this scholarship
    check_scholarship_permission(current_user, rule.scholarship_type_id)

    # Update only fields defined in the Pydantic schema to prevent mass assignment
    # This automatically stays in sync with schema changes
    allowed_fields = set(rule_data.model_fields.keys())
    allowed_fields.add("updated_by")  # Allow system field

    update_data = rule_data.dict(exclude_unset=True)
    update_data["updated_by"] = current_user.id

    for field, value in update_data.items():
        if field in allowed_fields and hasattr(rule, field):
            setattr(rule, field, value)

    await db.commit()

    # Load relationships in a single query
    refreshed_rule_stmt = (
        select(ScholarshipRule)
        .options(
            selectinload(ScholarshipRule.scholarship_type),
            selectinload(ScholarshipRule.creator),
            selectinload(ScholarshipRule.updater),
        )
        .where(ScholarshipRule.id == rule.id)
    )

    refreshed_result = await db.execute(refreshed_rule_stmt)
    rule = refreshed_result.scalar_one()

    rule_response = ScholarshipRuleResponse.model_validate(rule)
    rule_response.academic_period_label = rule.academic_period_label

    return {"success": True, "message": "Scholarship rule updated successfully", "data": rule_response}


@router.delete("/scholarship-rules/{id}")
async def delete_scholarship_rule(
    id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Delete a scholarship rule"""

    # Get existing rule
    stmt = select(ScholarshipRule).where(ScholarshipRule.id == id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scholarship rule not found")

    # Check permission to manage this scholarship
    check_scholarship_permission(current_user, rule.scholarship_type_id)

    await db.delete(rule)
    await db.commit()

    return {
        "success": True,
        "message": "Scholarship rule deleted successfully",
        "data": {"message": "Rule deleted successfully"},
    }


async def _copy_rules_in_batches(
    db: AsyncSession,
    base_stmt: Select,
    copy_request: RuleCopyRequest,
    target_semester_enum,
    current_user: User,
    total_rules: int,
    batch_size: int,
) -> ApiResponse[List[ScholarshipRuleResponse]]:
    """Process rule copying in batches to manage memory usage for large datasets"""

    all_new_rules = []
    total_skipped = 0
    processed_count = 0

    # Optimized duplicate check function
    def rule_exists_in_target(source_rule):
        exists_query = (
            select(1)
            .where(
                ScholarshipRule.academic_year == copy_request.target_academic_year,
                ScholarshipRule.semester == target_semester_enum,
                ScholarshipRule.scholarship_type_id == source_rule.scholarship_type_id,
                ScholarshipRule.rule_name == source_rule.rule_name,
                ScholarshipRule.rule_type == source_rule.rule_type,
                ScholarshipRule.condition_field == source_rule.condition_field,
                ScholarshipRule.operator == source_rule.operator,
                ScholarshipRule.expected_value == source_rule.expected_value,
                ScholarshipRule.sub_type == source_rule.sub_type,
                ScholarshipRule.is_template.is_(False),
            )
            .exists()
        )
        return select(exists_query)

    # Process in batches
    offset = 0

    while offset < total_rules:
        # Get current batch
        batch_stmt = base_stmt.offset(offset).limit(batch_size)
        batch_result = await db.execute(batch_stmt)
        batch_rules = batch_result.scalars().all()

        if not batch_rules:
            break

        # Check permissions for batch
        scholarship_type_ids = set(rule.scholarship_type_id for rule in batch_rules)
        for scholarship_type_id in scholarship_type_ids:
            check_scholarship_permission(current_user, scholarship_type_id)

        # Process batch
        batch_new_rules = []
        batch_skipped = 0

        for source_rule in batch_rules:
            # Check for duplicates if not overwriting
            if not copy_request.overwrite_existing:
                exists_result = await db.execute(rule_exists_in_target(source_rule))
                if exists_result.scalar():
                    batch_skipped += 1
                    continue

            # Create copy
            new_rule = source_rule.create_copy_for_period(copy_request.target_academic_year, target_semester_enum)
            new_rule.created_by = current_user.id
            new_rule.updated_by = current_user.id
            batch_new_rules.append(new_rule)

        # Bulk insert batch
        if batch_new_rules:
            db.add_all(batch_new_rules)
            await db.commit()
            all_new_rules.extend(batch_new_rules)

        total_skipped += batch_skipped
        processed_count += len(batch_rules)
        offset += batch_size

    # Load relationships for response
    if all_new_rules:
        rule_ids = [rule.id for rule in all_new_rules]
        refreshed_rules_stmt = (
            select(ScholarshipRule)
            .options(
                selectinload(ScholarshipRule.scholarship_type),
                selectinload(ScholarshipRule.creator),
                selectinload(ScholarshipRule.updater),
            )
            .where(ScholarshipRule.id.in_(rule_ids))
        )

        refreshed_result = await db.execute(refreshed_rules_stmt)
        refreshed_rules = refreshed_result.scalars().all()

        rule_responses = []
        for rule in refreshed_rules:
            rule_response = ScholarshipRuleResponse.model_validate(rule)
            rule_response.academic_period_label = rule.academic_period_label
            rule_responses.append(rule_response)
    else:
        rule_responses = []

    # Build response message
    if total_skipped > 0:
        message = f"Successfully copied {len(all_new_rules)} rules in batches. Skipped {total_skipped} duplicates."
    else:
        message = f"Successfully copied {len(all_new_rules)} rules in batches."

    return {"success": True, "message": message, "data": rule_responses}


@router.post("/scholarship-rules/copy")
async def copy_rules_between_periods(
    copy_request: RuleCopyRequest, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Copy rules between academic periods"""

    # Build source query
    stmt = select(ScholarshipRule)

    # Filter by source period
    if copy_request.source_academic_year:
        stmt = stmt.where(ScholarshipRule.academic_year == copy_request.source_academic_year)

    if copy_request.source_semester:
        # source_semester is already a Semester enum from the schema
        stmt = stmt.where(ScholarshipRule.semester == copy_request.source_semester)

    # Filter by scholarship types if specified
    if copy_request.scholarship_type_ids:
        stmt = stmt.where(ScholarshipRule.scholarship_type_id.in_(copy_request.scholarship_type_ids))

    # Filter by specific rules if specified
    if copy_request.rule_ids:
        stmt = stmt.where(ScholarshipRule.id.in_(copy_request.rule_ids))

    # Exclude templates
    stmt = stmt.where(ScholarshipRule.is_template.is_(False))

    # Get count first to decide on batch processing approach
    count_stmt = select(func.count(ScholarshipRule.id))
    if copy_request.rule_ids:
        count_stmt = count_stmt.where(ScholarshipRule.id.in_(copy_request.rule_ids))
    else:
        count_stmt = count_stmt.where(
            ScholarshipRule.scholarship_type_id == copy_request.source_scholarship_type_id,
            ScholarshipRule.academic_year == copy_request.source_academic_year,
        )
        if copy_request.source_semester:
            count_stmt = count_stmt.where(ScholarshipRule.semester == copy_request.source_semester)

    count_stmt = count_stmt.where(ScholarshipRule.is_template.is_(False))
    count_result = await db.execute(count_stmt)
    total_rules = count_result.scalar()

    if total_rules == 0:
        return {"success": True, "message": "No rules found to copy", "data": []}

    # For large datasets (>500 rules), use batch processing to avoid memory issues
    BATCH_SIZE = 500
    use_batch_processing = total_rules > BATCH_SIZE

    target_semester_enum = copy_request.target_semester

    if use_batch_processing:
        # Process in batches for large datasets
        return await _copy_rules_in_batches(
            db, stmt, copy_request, target_semester_enum, current_user, total_rules, BATCH_SIZE
        )
    else:
        # Process all at once for smaller datasets
        result = await db.execute(stmt)
        source_rules = result.scalars().all()

        # Check permissions for all scholarship types involved
        scholarship_type_ids = set(rule.scholarship_type_id for rule in source_rules)
        for scholarship_type_id in scholarship_type_ids:
            check_scholarship_permission(current_user, scholarship_type_id)

    # Create copies with bulk duplicate checking for better performance
    new_rules = []
    skipped_rules = 0

    # Optimized duplicate check using EXISTS subquery for better performance with large datasets
    def rule_exists_in_target(source_rule):
        """Check if a rule already exists in the target period using EXISTS subquery"""
        exists_query = (
            select(1)
            .where(
                ScholarshipRule.academic_year == copy_request.target_academic_year,
                ScholarshipRule.semester == target_semester_enum,
                ScholarshipRule.scholarship_type_id == source_rule.scholarship_type_id,
                ScholarshipRule.rule_name == source_rule.rule_name,
                ScholarshipRule.rule_type == source_rule.rule_type,
                ScholarshipRule.condition_field == source_rule.condition_field,
                ScholarshipRule.operator == source_rule.operator,
                ScholarshipRule.expected_value == source_rule.expected_value,
                ScholarshipRule.sub_type == source_rule.sub_type,
                ScholarshipRule.is_template.is_(False),  # Exclude templates
            )
            .exists()
        )

        return select(exists_query)

    for source_rule in source_rules:
        # Check if rule already exists using EXISTS subquery (more memory efficient)
        if not copy_request.overwrite_existing:
            exists_result = await db.execute(rule_exists_in_target(source_rule))
            rule_exists = exists_result.scalar()

            if rule_exists:
                # Skip this rule as it already exists
                skipped_rules += 1
                continue

        # Create new rule
        new_rule = source_rule.create_copy_for_period(copy_request.target_academic_year, target_semester_enum)
        new_rule.created_by = current_user.id
        new_rule.updated_by = current_user.id
        new_rules.append(new_rule)

    # Add all new rules
    db.add_all(new_rules)
    await db.commit()

    # Load all relationships in a single batch query
    if new_rules:
        rule_ids = [rule.id for rule in new_rules]
        refreshed_rules_stmt = (
            select(ScholarshipRule)
            .options(
                selectinload(ScholarshipRule.scholarship_type),
                selectinload(ScholarshipRule.creator),
                selectinload(ScholarshipRule.updater),
            )
            .where(ScholarshipRule.id.in_(rule_ids))
        )

        refreshed_result = await db.execute(refreshed_rules_stmt)
        refreshed_rules = refreshed_result.scalars().all()

        # Create response objects
        rule_responses = []
        for rule in refreshed_rules:
            rule_response = ScholarshipRuleResponse.model_validate(rule)
            rule_response.academic_period_label = rule.academic_period_label
            rule_responses.append(rule_response)
    else:
        rule_responses = []

    # Build response message
    if skipped_rules > 0:
        message = (
            f"Successfully copied {len(new_rules)} rules to target period. Skipped {skipped_rules} duplicate rules."
        )
    else:
        message = f"Successfully copied {len(new_rules)} rules to target period."

    return {"success": True, "message": message, "data": rule_responses}


@router.post("/scholarship-rules/bulk-operation")
async def bulk_rule_operation(
    operation_request: BulkRuleOperation,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Perform bulk operations on scholarship rules"""

    if not operation_request.rule_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No rule IDs provided")

    # Get rules
    stmt = select(ScholarshipRule).where(ScholarshipRule.id.in_(operation_request.rule_ids))
    result = await db.execute(stmt)
    rules = result.scalars().all()

    if not rules:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No rules found with the provided IDs")

    # Check permissions for all scholarship types involved
    scholarship_type_ids = set(rule.scholarship_type_id for rule in rules)
    for scholarship_type_id in scholarship_type_ids:
        check_scholarship_permission(current_user, scholarship_type_id)

    operation_results = {"operation": operation_request.operation, "affected_rules": len(rules), "details": []}

    if operation_request.operation == "activate":
        for rule in rules:
            rule.is_active = True
            rule.updated_by = current_user.id
        await db.commit()
        operation_results["details"].append(f"Activated {len(rules)} rules")

    elif operation_request.operation == "deactivate":
        for rule in rules:
            rule.is_active = False
            rule.updated_by = current_user.id
        await db.commit()
        operation_results["details"].append(f"Deactivated {len(rules)} rules")

    elif operation_request.operation == "delete":
        for rule in rules:
            await db.delete(rule)
        await db.commit()
        operation_results["details"].append(f"Deleted {len(rules)} rules")

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported operation: {operation_request.operation}"
        )

    return {
        "success": True,
        "message": f"Bulk operation '{operation_request.operation}' completed successfully",
        "data": operation_results,
    }


# ============================
# Rule Template Management
# ============================


@router.get("/scholarship-rules/templates")
async def get_rule_templates(
    scholarship_type_id: Optional[int] = Query(None, description="Filter by scholarship type"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all rule templates"""

    # Check scholarship permission if specific scholarship type is requested
    if scholarship_type_id:
        check_scholarship_permission(current_user, scholarship_type_id)

    stmt = (
        select(ScholarshipRule)
        .options(selectinload(ScholarshipRule.scholarship_type), selectinload(ScholarshipRule.creator))
        .where(ScholarshipRule.is_template.is_(True))
    )

    if scholarship_type_id:
        stmt = stmt.where(ScholarshipRule.scholarship_type_id == scholarship_type_id)
    elif not current_user.is_super_admin():
        # If no specific scholarship type requested and user is not super admin,
        # only show templates for scholarships they have permission to manage
        admin_scholarship_ids = [
            admin_scholarship.scholarship_id for admin_scholarship in current_user.admin_scholarships
        ]
        if admin_scholarship_ids:
            stmt = stmt.where(ScholarshipRule.scholarship_type_id.in_(admin_scholarship_ids))
        else:
            # Admin has no scholarship permissions, return empty result
            return {"success": True, "message": "No rule templates found", "data": []}

    stmt = stmt.order_by(ScholarshipRule.template_name, ScholarshipRule.priority.desc())

    result = await db.execute(stmt)
    templates = result.scalars().all()

    template_responses = []
    for template in templates:
        # Ensure all attributes are loaded in the session context
        await db.refresh(template)

        template_response = ScholarshipRuleResponse.model_validate(template)
        template_response.academic_period_label = template.academic_period_label
        template_responses.append(template_response)

    return {
        "success": True,
        "message": f"Retrieved {len(template_responses)} rule templates",
        "data": template_responses,
    }


@router.post("/scholarship-rules/create-template")
async def create_rule_template(
    template_request: RuleTemplateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a rule template from existing rules"""

    # Get the source rules
    stmt = select(ScholarshipRule).where(ScholarshipRule.id.in_(template_request.rule_ids))
    result = await db.execute(stmt)
    source_rules = result.scalars().all()

    if not source_rules:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No rules found with the provided IDs")

    # Check permissions for all scholarship types involved
    scholarship_type_ids = set(rule.scholarship_type_id for rule in source_rules)
    for scholarship_type_id in scholarship_type_ids:
        check_scholarship_permission(current_user, scholarship_type_id)

    # Verify all rules belong to the same scholarship type
    if not all(rule.scholarship_type_id == template_request.scholarship_type_id for rule in source_rules):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="All rules must belong to the same scholarship type"
        )

    # Create template rules
    template_rules = []
    for source_rule in source_rules:
        template_rule = ScholarshipRule(
            scholarship_type_id=source_rule.scholarship_type_id,
            sub_type=source_rule.sub_type,
            academic_year=None,  # Templates don't have academic context
            semester=None,
            is_template=True,
            template_name=template_request.template_name,
            template_description=template_request.template_description,
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
            is_active=True,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        template_rules.append(template_rule)

    # Add template rules to database
    db.add_all(template_rules)
    await db.commit()

    # Load all relationships in a single batch query
    if template_rules:
        rule_ids = [rule.id for rule in template_rules]
        refreshed_rules_stmt = (
            select(ScholarshipRule)
            .options(
                selectinload(ScholarshipRule.scholarship_type),
                selectinload(ScholarshipRule.creator),
                selectinload(ScholarshipRule.updater),
            )
            .where(ScholarshipRule.id.in_(rule_ids))
        )

        refreshed_result = await db.execute(refreshed_rules_stmt)
        refreshed_rules = refreshed_result.scalars().all()

        # Create response objects
        template_responses = []
        for rule in refreshed_rules:
            rule_response = ScholarshipRuleResponse.model_validate(rule)
            rule_response.academic_period_label = rule.academic_period_label
            template_responses.append(rule_response)
    else:
        template_responses = []

    return {
        "success": True,
        "message": f"Created template '{template_request.template_name}' with {len(template_rules)} rules",
        "data": template_responses,
    }


@router.post("/scholarship-rules/apply-template")
async def apply_rule_template(
    template_request: ApplyTemplateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Apply a rule template to create rules for a specific academic period"""

    # Get template rules
    stmt = select(ScholarshipRule).where(
        ScholarshipRule.id == template_request.template_id, ScholarshipRule.is_template.is_(True)
    )
    result = await db.execute(stmt)
    template_rule = result.scalar_one_or_none()

    if not template_rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    # Check permission to manage the target scholarship
    check_scholarship_permission(current_user, template_request.scholarship_type_id)

    # Get all rules with the same template name and scholarship type
    template_stmt = select(ScholarshipRule).where(
        ScholarshipRule.template_name == template_rule.template_name,
        ScholarshipRule.scholarship_type_id == template_request.scholarship_type_id,
        ScholarshipRule.is_template.is_(True),
    )
    template_result = await db.execute(template_stmt)
    template_rules = template_result.scalars().all()

    # Check for existing rules in the target period if not overwriting
    if not template_request.overwrite_existing:
        target_semester_enum = None
        if template_request.semester:
            target_semester_enum = Semester.first if template_request.semester == "first" else Semester.second

        existing_stmt = select(ScholarshipRule).where(
            ScholarshipRule.scholarship_type_id == template_request.scholarship_type_id,
            ScholarshipRule.academic_year == template_request.academic_year,
            ScholarshipRule.semester == target_semester_enum,
            ScholarshipRule.is_template.is_(False),
        )

        existing_result = await db.execute(existing_stmt)
        existing_rules = existing_result.scalars().all()

        if existing_rules:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Rules already exist for the target period. Use overwrite_existing=true to replace them.",
            )

    # Create rules from template
    new_rules = []
    target_semester_enum = None
    if template_request.semester:
        target_semester_enum = Semester.first if template_request.semester == "first" else Semester.second

    for template_rule in template_rules:
        new_rule = ScholarshipRule(
            scholarship_type_id=template_request.scholarship_type_id,
            sub_type=template_rule.sub_type,
            academic_year=template_request.academic_year,
            semester=target_semester_enum,
            is_template=False,
            rule_name=template_rule.rule_name,
            rule_type=template_rule.rule_type,
            tag=template_rule.tag,
            description=template_rule.description,
            condition_field=template_rule.condition_field,
            operator=template_rule.operator,
            expected_value=template_rule.expected_value,
            message=template_rule.message,
            message_en=template_rule.message_en,
            is_hard_rule=template_rule.is_hard_rule,
            is_warning=template_rule.is_warning,
            priority=template_rule.priority,
            is_active=template_rule.is_active,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        new_rules.append(new_rule)

    # Add new rules to database
    db.add_all(new_rules)
    await db.commit()

    # Load all relationships in a single batch query
    if new_rules:
        rule_ids = [rule.id for rule in new_rules]
        refreshed_rules_stmt = (
            select(ScholarshipRule)
            .options(
                selectinload(ScholarshipRule.scholarship_type),
                selectinload(ScholarshipRule.creator),
                selectinload(ScholarshipRule.updater),
            )
            .where(ScholarshipRule.id.in_(rule_ids))
        )

        refreshed_result = await db.execute(refreshed_rules_stmt)
        refreshed_rules = refreshed_result.scalars().all()

        # Create response objects
        rule_responses = []
        for rule in refreshed_rules:
            rule_response = ScholarshipRuleResponse.model_validate(rule)
            rule_response.academic_period_label = rule.academic_period_label
            rule_responses.append(rule_response)
    else:
        rule_responses = []

    return {
        "success": True,
        "message": f"Applied template '{template_rule.template_name}' and created {len(new_rules)} rules",
        "data": rule_responses,
    }


@router.delete("/scholarship-rules/templates/{template_name}")
async def delete_rule_template(
    template_name: str,
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a rule template and all its associated rules"""

    # Check permission to manage this scholarship
    check_scholarship_permission(current_user, scholarship_type_id)

    # Get template rules
    stmt = select(ScholarshipRule).where(
        ScholarshipRule.template_name == template_name,
        ScholarshipRule.scholarship_type_id == scholarship_type_id,
        ScholarshipRule.is_template.is_(True),
    )
    result = await db.execute(stmt)
    template_rules = result.scalars().all()

    if not template_rules:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    # Delete all template rules
    for rule in template_rules:
        await db.delete(rule)

    await db.commit()

    return {
        "success": True,
        "message": f"Deleted template '{template_name}' with {len(template_rules)} rules",
        "data": {"message": f"Template '{template_name}' deleted successfully"},
    }


@router.get("/scholarships/available-years")
async def get_available_years(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Get available academic years from scholarship rules"""

    # Query distinct academic years from scholarship rules
    stmt = (
        select(ScholarshipRule.academic_year)
        .distinct()
        .where(ScholarshipRule.academic_year.is_not(None))
        .order_by(ScholarshipRule.academic_year.desc())
    )

    result = await db.execute(stmt)
    years = result.scalars().all()

    # If no years found in database, provide default years
    if not years:
        # Current year in Taiwan calendar (民國)
        from datetime import datetime

        current_taiwan_year = datetime.now().year - 1911
        years = [current_taiwan_year - 1, current_taiwan_year, current_taiwan_year + 1]

    return {"success": True, "message": f"Retrieved {len(years)} available years", "data": list(years)}
