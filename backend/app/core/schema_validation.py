"""
Schema validation utilities to prevent ResponseValidationError

These utilities help developers catch schema validation issues early
during development before they reach production.
"""

from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, ValidationError
from datetime import datetime
from decimal import Decimal
import enum
import logging

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Custom exception for schema validation errors"""
    pass


def validate_response_data(data: Any, schema: Type[BaseModel]) -> bool:
    """
    Validate response data against a Pydantic schema
    
    Args:
        data: The data to validate (dict, list of dicts, or single object)
        schema: The Pydantic model class to validate against
        
    Returns:
        bool: True if validation passes
        
    Raises:
        SchemaValidationError: If validation fails
    """
    try:
        if isinstance(data, list):
            for item in data:
                schema.model_validate(item)
        else:
            schema.model_validate(data)
        return True
    except ValidationError as e:
        error_details = []
        for error in e.errors():
            field_path = " -> ".join(str(loc) for loc in error['loc'])
            error_details.append(f"Field '{field_path}': {error['msg']}")
        
        raise SchemaValidationError(
            f"Schema validation failed for {schema.__name__}:\n" + 
            "\n".join(error_details)
        )


def convert_sqlalchemy_to_response_dict(
    obj: Any, 
    exclude_fields: Optional[List[str]] = None,
    include_relationships: bool = False
) -> Dict[str, Any]:
    """
    Convert SQLAlchemy model instance to dictionary suitable for API responses
    
    Args:
        obj: SQLAlchemy model instance
        exclude_fields: List of field names to exclude
        include_relationships: Whether to include relationship fields
        
    Returns:
        dict: Converted dictionary with proper serialization
    """
    if exclude_fields is None:
        exclude_fields = []
    
    result = {}
    
    # Handle SQLAlchemy model columns
    if hasattr(obj, '__table__'):
        for column in obj.__table__.columns:
            if column.name in exclude_fields:
                continue
                
            value = getattr(obj, column.name)
            result[column.name] = serialize_value(value)
    
    # Handle relationships if requested
    if include_relationships and hasattr(obj, '__mapper__'):
        for relationship in obj.__mapper__.relationships:
            if relationship.key in exclude_fields:
                continue
                
            value = getattr(obj, relationship.key)
            if value is not None:
                if relationship.uselist:  # One-to-many or many-to-many
                    result[relationship.key] = [
                        convert_sqlalchemy_to_response_dict(item, exclude_fields, False)
                        for item in value
                    ]
                else:  # One-to-one or many-to-one
                    result[relationship.key] = convert_sqlalchemy_to_response_dict(
                        value, exclude_fields, False
                    )
    
    return result


def serialize_value(value: Any) -> Any:
    """
    Serialize a value for JSON response
    
    Args:
        value: The value to serialize
        
    Returns:
        Any: Serialized value
    """
    if value is None:
        return None
    
    # Handle enum values
    if isinstance(value, enum.Enum):
        return value.value
    
    # Handle datetime objects
    if isinstance(value, datetime):
        return value.isoformat()
    
    # Handle Decimal objects
    if isinstance(value, Decimal):
        return float(value)
    
    # Handle other types that need special serialization
    if hasattr(value, 'isoformat'):  # Date objects
        return value.isoformat()
    
    return value


def create_response_converter(
    source_model: Type,
    target_schema: Type[BaseModel],
    field_mapping: Optional[Dict[str, str]] = None,
    custom_converters: Optional[Dict[str, callable]] = None
):
    """
    Create a converter function from SQLAlchemy model to Pydantic response schema
    
    Args:
        source_model: SQLAlchemy model class
        target_schema: Pydantic response schema class
        field_mapping: Map source field names to target field names
        custom_converters: Custom conversion functions for specific fields
        
    Returns:
        callable: Converter function
    """
    if field_mapping is None:
        field_mapping = {}
    
    if custom_converters is None:
        custom_converters = {}
    
    def converter(source_obj) -> target_schema:
        """Convert source object to target schema"""
        data = convert_sqlalchemy_to_response_dict(source_obj)
        
        # Apply field mapping
        converted_data = {}
        for source_field, value in data.items():
            target_field = field_mapping.get(source_field, source_field)
            
            # Apply custom converter if available
            if source_field in custom_converters:
                value = custom_converters[source_field](value)
            
            converted_data[target_field] = value
        
        # Add any missing required fields with default values
        schema_fields = target_schema.model_fields
        for field_name, field_info in schema_fields.items():
            if field_name not in converted_data:
                if hasattr(field_info, 'default') and field_info.default is not None:
                    converted_data[field_name] = field_info.default
                elif field_name in ['passed', 'warnings', 'errors']:
                    # Common pattern for validation results
                    converted_data[field_name] = []
        
        return target_schema(**converted_data)
    
    return converter


def debug_response_schema_mismatch(
    response_data: Any,
    expected_schema: Type[BaseModel],
    logger_name: str = __name__
) -> None:
    """
    Debug helper to identify schema mismatches
    
    Args:
        response_data: The actual response data
        expected_schema: The expected Pydantic schema
        logger_name: Logger name to use
    """
    debug_logger = logging.getLogger(logger_name)
    
    try:
        validate_response_data(response_data, expected_schema)
        debug_logger.info(f"✅ Schema validation passed for {expected_schema.__name__}")
    except SchemaValidationError as e:
        debug_logger.error(f"❌ Schema validation failed for {expected_schema.__name__}")
        debug_logger.error(f"Error details: {e}")
        
        if isinstance(response_data, dict):
            actual_fields = set(response_data.keys())
            expected_fields = set(expected_schema.model_fields.keys())
            
            missing_fields = expected_fields - actual_fields
            extra_fields = actual_fields - expected_fields
            
            if missing_fields:
                debug_logger.error(f"Missing fields: {missing_fields}")
            
            if extra_fields:
                debug_logger.warning(f"Extra fields: {extra_fields}")
            
            # Check field types
            for field_name, field_value in response_data.items():
                if field_name in expected_schema.model_fields:
                    expected_type = expected_schema.model_fields[field_name].annotation
                    actual_type = type(field_value).__name__
                    debug_logger.debug(f"Field '{field_name}': expected {expected_type}, got {actual_type}")


# Decorator for automatic response validation in development
def validate_response_schema(schema: Type[BaseModel]):
    """
    Decorator to automatically validate API response schemas in development
    
    Usage:
        @validate_response_schema(MyResponseSchema)
        async def my_endpoint():
            return data
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # Only validate in development/debug mode
            from app.core.config import settings
            if settings.debug:
                try:
                    validate_response_data(result, schema)
                    logger.debug(f"✅ Response schema validation passed for {func.__name__}")
                except SchemaValidationError as e:
                    logger.error(f"❌ Response schema validation failed for {func.__name__}: {e}")
                    # In development, we might want to raise the error
                    # In production, we might want to log and continue
                    raise
            
            return result
        return wrapper
    return decorator


# Example usage patterns
EXAMPLE_USAGE = """
# Example 1: Manual validation
from app.schemas.scholarship import EligibleScholarshipResponse

scholarships = get_scholarships_from_db()
response_data = [convert_sqlalchemy_to_response_dict(s) for s in scholarships]

try:
    validate_response_data(response_data, EligibleScholarshipResponse)
    return response_data
except SchemaValidationError as e:
    logger.error(f"Schema validation failed: {e}")
    # Handle the error appropriately

# Example 2: Using converter
converter = create_response_converter(
    ScholarshipType,
    EligibleScholarshipResponse,
    field_mapping={'semester': 'semester'},
    custom_converters={
        'semester': lambda x: x.value if hasattr(x, 'value') else x,
        'eligible_sub_types': lambda x: x or ['general']  
    }
)

scholarships = get_scholarships_from_db()
response_data = [converter(s) for s in scholarships]
return response_data

# Example 3: Using decorator
@validate_response_schema(EligibleScholarshipResponse)
async def get_eligible_scholarships():
    # Your endpoint implementation
    return response_data
"""