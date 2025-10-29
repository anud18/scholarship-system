"""
Admin System Configuration Management API Endpoints

Handles system configuration operations including:
- Configuration CRUD
- Bulk updates
- Validation
- Encrypted value handling
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db
from app.models.system_setting import ConfigCategory
from app.models.user import User
from app.schemas.config_management import (
    ConfigurationBulkUpdateSchema,
    ConfigurationCategorySchema,
    ConfigurationCreateSchema,
    ConfigurationItemWithDecryptedValueSchema,
    ConfigurationValidationResultSchema,
    ConfigurationValidationSchema,
    get_category_description,
    get_category_display_name,
    mask_sensitive_value,
)
from app.services.config_management_service import ConfigurationService

from ._helpers import require_super_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/configurations")
async def get_all_configurations(
    category: Optional[ConfigCategory] = Query(None, description="Filter by category"),
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all system configurations organized by category (super admin only)"""
    try:
        config_service = ConfigurationService(db)

        if category:
            # Get specific category
            settings = await config_service.get_configurations_by_category(category)
            categories = [category]
        else:
            # Get all categories
            settings = await config_service.get_all_configurations()
            categories = list(ConfigCategory)

        # Organize by category
        result = []
        for cat in categories:
            cat_settings = [s for s in settings if s.category == cat]

            # Transform settings with decrypted values
            config_items = []
            for setting in cat_settings:
                decrypted_value = await config_service.get_decrypted_value(setting)
                display_value = mask_sensitive_value(str(decrypted_value), setting.is_sensitive)

                # Get modifier username
                modifier_username = None
                if setting.last_modified_by:
                    modifier_stmt = select(User).where(User.id == setting.last_modified_by)
                    modifier_result = await db.execute(modifier_stmt)
                    modifier = modifier_result.scalar_one_or_none()
                    modifier_username = modifier.nycu_id if modifier else None

                config_items.append(
                    ConfigurationItemWithDecryptedValueSchema(
                        key=setting.key,
                        decrypted_value=decrypted_value,
                        display_value=display_value,
                        category=setting.category,
                        data_type=setting.data_type,
                        is_sensitive=setting.is_sensitive,
                        is_readonly=setting.is_readonly,
                        description=setting.description,
                        validation_regex=setting.validation_regex,
                        default_value=setting.default_value,
                        last_modified_by=setting.last_modified_by,
                        modified_by_username=modifier_username,
                        created_at=setting.created_at,
                        updated_at=setting.updated_at,
                    )
                )

            category_schema = ConfigurationCategorySchema(
                category=cat,
                display_name=get_category_display_name(cat),
                description=get_category_description(cat),
                configurations=config_items,
                total_count=len(config_items),
                sensitive_count=sum(1 for item in config_items if item.is_sensitive),
                readonly_count=sum(1 for item in config_items if item.is_readonly),
            )

            if config_items or not category:  # Include empty categories only when showing all
                result.append(category_schema)

        return {"success": True, "message": "Configurations retrieved successfully", "data": result}

    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving configurations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve configurations due to a database error.",
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving configurations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve configurations due to an unexpected error.",
        )


@router.post("/configurations")
async def create_configuration(
    config: ConfigurationCreateSchema,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new configuration (super admin only)"""
    try:
        config_service = ConfigurationService(db)

        # Validate the configuration
        is_valid, message = await config_service.validate_configuration(config.key, config.value, config.data_type)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid configuration value: {message}"
            )

        # Create the configuration
        setting = await config_service.set_configuration(
            key=config.key,
            value=config.value,
            user_id=current_user.id,
            category=config.category,
            data_type=config.data_type,
            is_sensitive=config.is_sensitive,
            is_readonly=config.is_readonly,
            description=config.description,
            validation_regex=config.validation_regex,
            default_value=config.default_value,
            change_reason=config.change_reason,
        )

        # Prepare response with decrypted value
        decrypted_value = await config_service.get_decrypted_value(setting)
        display_value = mask_sensitive_value(str(decrypted_value), setting.is_sensitive)

        response_data = ConfigurationItemWithDecryptedValueSchema(
            key=setting.key,
            decrypted_value=decrypted_value,
            display_value=display_value,
            category=setting.category,
            data_type=setting.data_type,
            is_sensitive=setting.is_sensitive,
            is_readonly=setting.is_readonly,
            description=setting.description,
            validation_regex=setting.validation_regex,
            default_value=setting.default_value,
            last_modified_by=setting.last_modified_by,
            modified_by_username=current_user.nycu_id,
            created_at=setting.created_at,
            updated_at=setting.updated_at,
        )

        return {"success": True, "message": f"Configuration '{config.key}' created successfully", "data": response_data}

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Database error creating configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create configuration due to a database error.",
        )
    except Exception as e:
        logger.error(f"Unexpected error creating configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create configuration due to an unexpected error.",
        )


@router.put("/configurations/bulk")
async def bulk_update_configurations(
    update_request: ConfigurationBulkUpdateSchema,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update multiple configurations (super admin only)"""
    try:
        config_service = ConfigurationService(db)

        # Validate all updates first
        for update in update_request.updates:
            existing = await config_service.get_configuration(update.key)
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration '{update.key}' not found"
                )

            is_valid, message = await config_service.validate_configuration(
                update.key, update.value, existing.data_type
            )
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid value for '{update.key}': {message}"
                )

        # Perform bulk update
        updates_data = []
        for update in update_request.updates:
            existing = await config_service.get_configuration(update.key)
            updates_data.append(
                {
                    "key": update.key,
                    "value": update.value,
                    "category": existing.category,
                    "data_type": existing.data_type,
                    "is_sensitive": existing.is_sensitive,
                    "is_readonly": existing.is_readonly,
                    "description": existing.description,
                    "validation_regex": existing.validation_regex,
                    "default_value": existing.default_value,
                }
            )

        updated_settings = await config_service.bulk_update_configurations(
            updates_data, current_user.id, update_request.change_reason
        )

        # Prepare response
        response_data = []
        for setting in updated_settings:
            decrypted_value = await config_service.get_decrypted_value(setting)
            display_value = mask_sensitive_value(str(decrypted_value), setting.is_sensitive)

            response_data.append(
                ConfigurationItemWithDecryptedValueSchema(
                    key=setting.key,
                    decrypted_value=decrypted_value,
                    display_value=display_value,
                    category=setting.category,
                    data_type=setting.data_type,
                    is_sensitive=setting.is_sensitive,
                    is_readonly=setting.is_readonly,
                    description=setting.description,
                    validation_regex=setting.validation_regex,
                    default_value=setting.default_value,
                    last_modified_by=setting.last_modified_by,
                    modified_by_username=current_user.nycu_id,
                    created_at=setting.created_at,
                    updated_at=setting.updated_at,
                )
            )

        return {
            "success": True,
            "message": f"Successfully updated {len(updated_settings)} configurations",
            "data": response_data,
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in bulk configuration update: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update configurations due to a database error.",
        )
    except Exception as e:
        logger.error(f"Unexpected error in bulk configuration update: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update configurations due to an unexpected error.",
        )


@router.post("/configurations/validate")
async def validate_configuration(
    validation_request: ConfigurationValidationSchema,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Validate a configuration value (super admin only)"""
    try:
        config_service = ConfigurationService(db)

        is_valid, message = await config_service.validate_configuration(
            validation_request.key, validation_request.value, validation_request.data_type
        )

        # Additional regex validation if provided
        if is_valid and validation_request.validation_regex:
            from app.core.regex_validator import RegexValidationError, safe_regex_match

            try:
                match = safe_regex_match(
                    validation_request.validation_regex, str(validation_request.value), timeout_seconds=1
                )
                if not match:
                    is_valid = False
                    message = f"Value does not match pattern: {validation_request.validation_regex}"
            except RegexValidationError as e:
                is_valid = False
                message = f"Invalid regex pattern: {str(e)}"

        result = ConfigurationValidationResultSchema(
            is_valid=is_valid, message=message, suggested_value=None  # Could implement smart suggestions in the future
        )

        return {"success": True, "message": "Validation completed", "data": result}

    except Exception as e:
        logger.error(f"Unexpected error validating configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate configuration due to an unexpected error.",
        )


@router.delete("/configurations/{key}")
async def delete_configuration(
    key: str,
    change_reason: Optional[str] = Query(None, description="Reason for deletion"),
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a configuration (super admin only)"""
    try:
        config_service = ConfigurationService(db)

        success = await config_service.delete_configuration(key, current_user.id, change_reason)

        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration '{key}' not found")

        return {"success": True, "message": f"Configuration '{key}' deleted successfully", "data": key}

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Database error deleting configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete configuration due to a database error.",
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete configuration due to an unexpected error.",
        )
