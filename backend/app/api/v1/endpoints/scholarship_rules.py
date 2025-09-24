"""
Scholarship Rules Management API endpoints
Handles CRUD operations for scholarship eligibility rules
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_db
from app.core.security import require_admin
from app.models.enums import Semester
from app.models.scholarship import ScholarshipRule, ScholarshipType
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.scholarship import (
    BulkRuleOperation,
    RuleCopyRequest,
    ScholarshipRuleCreate,
    ScholarshipRuleResponse,
    ScholarshipRuleUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=ApiResponse[List[ScholarshipRuleResponse]])
async def list_scholarship_rules(
    scholarship_type_id: Optional[int] = Query(None, description="Filter by scholarship type ID"),
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    sub_type: Optional[str] = Query(None, description="Filter by sub type"),
    rule_type: Optional[str] = Query(None, description="Filter by rule type"),
    is_template: Optional[bool] = Query(None, description="Filter by template status"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List scholarship rules with filtering and pagination"""

    # Build query with filters
    stmt = select(ScholarshipRule).options(
        selectinload(ScholarshipRule.scholarship_type),
        selectinload(ScholarshipRule.creator),
        selectinload(ScholarshipRule.updater),
    )

    # Apply filters
    if scholarship_type_id:
        stmt = stmt.filter(ScholarshipRule.scholarship_type_id == scholarship_type_id)

    if academic_year:
        stmt = stmt.filter(
            or_(
                ScholarshipRule.academic_year == academic_year,
                ScholarshipRule.academic_year.is_(None),  # Include generic rules
            )
        )

    if semester:
        try:
            semester_enum = Semester(semester.lower())
            stmt = stmt.filter(
                or_(
                    ScholarshipRule.semester == semester_enum,
                    ScholarshipRule.semester.is_(None),  # Include generic rules
                )
            )
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid semester: {semester}")

    if sub_type:
        stmt = stmt.filter(
            or_(
                ScholarshipRule.sub_type == sub_type,
                ScholarshipRule.sub_type.is_(None),  # Include generic rules
            )
        )

    if rule_type:
        stmt = stmt.filter(ScholarshipRule.rule_type == rule_type)

    if is_template is not None:
        stmt = stmt.filter(ScholarshipRule.is_template == is_template)

    if is_active is not None:
        stmt = stmt.filter(ScholarshipRule.is_active == is_active)

    if tag:
        stmt = stmt.filter(ScholarshipRule.tag.ilike(f"%{tag}%"))

    # Apply sorting with whitelist validation to prevent SQL injection
    ALLOWED_SORT_FIELDS = {
        "id",
        "created_at",
        "updated_at",
        "rule_name",
        "priority",
        "scholarship_type_id",
        "tag",
        "is_active",
        "is_hard_rule",
        "is_warning",
    }

    if sort_by not in ALLOWED_SORT_FIELDS:
        sort_by = "created_at"

    order_field = getattr(ScholarshipRule, sort_by)
    if sort_order.lower() == "desc":
        stmt = stmt.order_by(desc(order_field))
    else:
        stmt = stmt.order_by(asc(order_field))

    # Apply pagination
    offset = (page - 1) * per_page
    stmt = stmt.offset(offset).limit(per_page)

    # Execute query
    result = await db.execute(stmt)
    rules = result.scalars().all()

    # Convert to response format
    response_rules = []
    for rule in rules:
        rule_dict = ScholarshipRuleResponse.model_validate(rule)
        rule_dict.academic_period_label = rule.academic_period_label
        response_rules.append(rule_dict)

    return ApiResponse(
        success=True,
        message=f"Retrieved {len(response_rules)} scholarship rules",
        data=response_rules,
    )


@router.post("/", response_model=ApiResponse[ScholarshipRuleResponse])
async def create_scholarship_rule(
    rule_data: ScholarshipRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new scholarship rule"""

    # Validate scholarship type exists
    scholarship_type_stmt = select(ScholarshipType).filter(ScholarshipType.id == rule_data.scholarship_type_id)
    scholarship_type_result = await db.execute(scholarship_type_stmt)
    scholarship_type = scholarship_type_result.scalar_one_or_none()

    if not scholarship_type:
        raise HTTPException(
            status_code=404,
            detail=f"Scholarship type {rule_data.scholarship_type_id} not found",
        )

    # Validate sub_type if provided
    if rule_data.sub_type:
        if not scholarship_type.sub_type_list or rule_data.sub_type not in scholarship_type.sub_type_list:
            raise HTTPException(
                status_code=400,
                detail=f"Sub-type '{rule_data.sub_type}' is not valid for scholarship type '{scholarship_type.name}'",
            )

    # Create rule
    rule = ScholarshipRule(**rule_data.model_dump(), created_by=current_user.id, updated_by=current_user.id)

    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    # Load relationships
    await db.refresh(rule, ["scholarship_type", "creator", "updater"])

    return ApiResponse(
        success=True,
        message=f"Created scholarship rule: {rule.rule_name}",
        data=ScholarshipRuleResponse.model_validate(rule),
    )


@router.get("/{rule_id}", response_model=ApiResponse[ScholarshipRuleResponse])
async def get_scholarship_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get a specific scholarship rule by ID"""

    stmt = (
        select(ScholarshipRule)
        .options(
            selectinload(ScholarshipRule.scholarship_type),
            selectinload(ScholarshipRule.creator),
            selectinload(ScholarshipRule.updater),
        )
        .filter(ScholarshipRule.id == rule_id)
    )

    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    return ApiResponse(
        success=True,
        message="Rule retrieved successfully",
        data=ScholarshipRuleResponse.model_validate(rule),
    )


@router.put("/{rule_id}", response_model=ApiResponse[ScholarshipRuleResponse])
async def update_scholarship_rule(
    rule_id: int,
    rule_update: ScholarshipRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update a scholarship rule"""

    # Get existing rule
    stmt = (
        select(ScholarshipRule)
        .options(selectinload(ScholarshipRule.scholarship_type))
        .filter(ScholarshipRule.id == rule_id)
    )

    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Validate sub_type if provided
    if rule_update.sub_type:
        scholarship_type = rule.scholarship_type
        if not scholarship_type.sub_type_list or rule_update.sub_type not in scholarship_type.sub_type_list:
            raise HTTPException(
                status_code=400,
                detail=f"Sub-type '{rule_update.sub_type}' is not valid for scholarship type '{scholarship_type.name}'",
            )

    # Update only fields defined in the Pydantic schema to prevent mass assignment
    # This automatically stays in sync with schema changes
    allowed_fields = set(rule_update.model_fields.keys())

    update_data = rule_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in allowed_fields and hasattr(rule, field):
            setattr(rule, field, value)

    rule.updated_by = current_user.id

    await db.commit()
    await db.refresh(rule)

    # Load relationships
    await db.refresh(rule, ["scholarship_type", "creator", "updater"])

    return ApiResponse(
        success=True,
        message=f"Updated scholarship rule: {rule.rule_name}",
        data=ScholarshipRuleResponse.model_validate(rule),
    )


@router.delete("/{rule_id}", response_model=ApiResponse[Dict[str, Any]])
async def delete_scholarship_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a scholarship rule"""

    stmt = select(ScholarshipRule).filter(ScholarshipRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule_name = rule.rule_name
    await db.delete(rule)
    await db.commit()

    return ApiResponse(
        success=True,
        message=f"Deleted scholarship rule: {rule_name}",
        data={"deleted_rule_id": rule_id},
    )


@router.post("/bulk", response_model=ApiResponse[Dict[str, Any]])
async def bulk_rule_operation(
    operation: BulkRuleOperation,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Perform bulk operations on scholarship rules"""

    # Get rules by IDs
    stmt = select(ScholarshipRule).filter(ScholarshipRule.id.in_(operation.rule_ids))
    result = await db.execute(stmt)
    rules = result.scalars().all()

    if len(rules) != len(operation.rule_ids):
        raise HTTPException(status_code=404, detail="Some rules not found")

    processed_count = 0

    if operation.operation == "activate":
        for rule in rules:
            rule.is_active = True
            rule.updated_by = current_user.id
            processed_count += 1

    elif operation.operation == "deactivate":
        for rule in rules:
            rule.is_active = False
            rule.updated_by = current_user.id
            processed_count += 1

    elif operation.operation == "delete":
        for rule in rules:
            await db.delete(rule)
            processed_count += 1

    else:
        raise HTTPException(status_code=400, detail=f"Unknown operation: {operation.operation}")

    await db.commit()

    return ApiResponse(
        success=True,
        message=f"Bulk {operation.operation} completed for {processed_count} rules",
        data={
            "operation": operation.operation,
            "processed_count": processed_count,
            "rule_ids": operation.rule_ids,
        },
    )


@router.post("/copy", response_model=ApiResponse[Dict[str, Any]])
async def copy_rules(
    copy_request: RuleCopyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Copy rules from one academic period to another"""

    # Build source query
    source_stmt = select(ScholarshipRule)

    if copy_request.source_academic_year:
        source_stmt = source_stmt.filter(ScholarshipRule.academic_year == copy_request.source_academic_year)

    if copy_request.source_semester:
        source_stmt = source_stmt.filter(ScholarshipRule.semester == copy_request.source_semester)

    if copy_request.scholarship_type_ids:
        source_stmt = source_stmt.filter(ScholarshipRule.scholarship_type_id.in_(copy_request.scholarship_type_ids))

    if copy_request.rule_ids:
        source_stmt = source_stmt.filter(ScholarshipRule.id.in_(copy_request.rule_ids))

    # Get source rules
    source_result = await db.execute(source_stmt)
    source_rules = source_result.scalars().all()

    if not source_rules:
        raise HTTPException(status_code=404, detail="No rules found to copy")

    copied_count = 0
    skipped_count = 0

    for source_rule in source_rules:
        # Check if target rule already exists
        target_stmt = select(ScholarshipRule).filter(
            and_(
                ScholarshipRule.scholarship_type_id == source_rule.scholarship_type_id,
                ScholarshipRule.academic_year == copy_request.target_academic_year,
                ScholarshipRule.semester == copy_request.target_semester,
                ScholarshipRule.rule_name == source_rule.rule_name,
                ScholarshipRule.rule_type == source_rule.rule_type,
                ScholarshipRule.sub_type == source_rule.sub_type,
            )
        )

        target_result = await db.execute(target_stmt)
        existing_rule = target_result.scalar_one_or_none()

        if existing_rule and not copy_request.overwrite_existing:
            skipped_count += 1
            continue

        if existing_rule and copy_request.overwrite_existing:
            # Update existing rule
            for field in [
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
            ]:
                setattr(existing_rule, field, getattr(source_rule, field))

            existing_rule.updated_by = current_user.id
            copied_count += 1
        else:
            # Create new rule
            new_rule_data = {
                "scholarship_type_id": source_rule.scholarship_type_id,
                "sub_type": source_rule.sub_type,
                "academic_year": copy_request.target_academic_year,
                "semester": copy_request.target_semester,
                "is_template": False,  # Copied rules are not templates
                "template_name": None,
                "template_description": None,
                "rule_name": source_rule.rule_name,
                "rule_type": source_rule.rule_type,
                "tag": source_rule.tag,
                "description": source_rule.description,
                "condition_field": source_rule.condition_field,
                "operator": source_rule.operator,
                "expected_value": source_rule.expected_value,
                "message": source_rule.message,
                "message_en": source_rule.message_en,
                "is_hard_rule": source_rule.is_hard_rule,
                "is_warning": source_rule.is_warning,
                "priority": source_rule.priority,
                "is_active": source_rule.is_active,
                "is_initial_enabled": source_rule.is_initial_enabled,
                "is_renewal_enabled": source_rule.is_renewal_enabled,
                "created_by": current_user.id,
                "updated_by": current_user.id,
            }

            new_rule = ScholarshipRule(**new_rule_data)
            db.add(new_rule)
            copied_count += 1

    await db.commit()

    return ApiResponse(
        success=True,
        message=f"Copied {copied_count} rules, skipped {skipped_count} existing rules",
        data={
            "copied_count": copied_count,
            "skipped_count": skipped_count,
            "source_period": f"AY{copy_request.source_academic_year} {copy_request.source_semester.value if copy_request.source_semester else 'All'}",
            "target_period": f"AY{copy_request.target_academic_year} {copy_request.target_semester.value if copy_request.target_semester else 'All'}",
        },
    )


@router.get(
    "/scholarship-types/{scholarship_type_id}/sub-types",
    response_model=ApiResponse[List[Dict[str, Any]]],
)
async def get_scholarship_type_sub_types(
    scholarship_type_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get available sub-types for a specific scholarship type"""

    # Get scholarship type
    stmt = (
        select(ScholarshipType)
        .options(selectinload(ScholarshipType.sub_type_configs))
        .filter(ScholarshipType.id == scholarship_type_id)
    )
    result = await db.execute(stmt)
    scholarship_type = result.scalar_one_or_none()

    if not scholarship_type:
        raise HTTPException(status_code=404, detail="Scholarship type not found")

    # Get sub-type list from the scholarship type
    sub_type_list = scholarship_type.sub_type_list or []

    # Get sub-type translations
    sub_type_translations = scholarship_type.get_sub_type_translations()

    # Build response with translation information
    sub_types = []

    # Always include "通用" option (null sub_type)
    sub_types.append({"value": None, "label": "通用", "label_en": "General", "is_default": True})

    # Add specific sub-types
    for sub_type in sub_type_list:
        if sub_type:  # Skip empty strings
            sub_types.append(
                {
                    "value": sub_type,
                    "label": sub_type_translations.get("zh", {}).get(sub_type, sub_type),
                    "label_en": sub_type_translations.get("en", {}).get(sub_type, sub_type),
                    "is_default": False,
                }
            )

    return ApiResponse(
        success=True,
        message=f"Sub-types for scholarship type {scholarship_type.name} retrieved successfully",
        data=sub_types,
    )
