"""
Automatic response conversion utilities

These utilities automatically convert SQLAlchemy models to Pydantic responses,
reducing boilerplate and preventing common schema validation errors.
"""

import inspect
from typing import Type, List, Dict, Any, Optional, get_origin, get_args
from functools import wraps
from pydantic import BaseModel
from sqlalchemy.ext.declarative import DeclarativeMeta
from datetime import datetime
from decimal import Decimal
import enum
import logging

logger = logging.getLogger(__name__)


def auto_convert_response(response_model: Type[BaseModel]):
    """
    Decorator that automatically converts SQLAlchemy models to Pydantic response models
    
    Usage:
        @router.get("/items", response_model=List[ItemResponse])
        @auto_convert_response(ItemResponse)
        async def get_items():
            items = await db.query(Item).all()
            return items  # Will be automatically converted
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            if result is None:
                return result
            
            # Convert the result
            converted_result = convert_to_response_model(result, response_model)
            
            logger.debug(f"Auto-converted response for {func.__name__}")
            return converted_result
        
        return wrapper
    return decorator


def convert_to_response_model(data: Any, response_model: Type[BaseModel]) -> Any:
    """
    Convert data to the specified response model
    
    Args:
        data: Raw data (SQLAlchemy model, list of models, etc.)
        response_model: Target Pydantic model
        
    Returns:
        Converted data matching the response model
    """
    if data is None:
        return None
    
    # Handle List[Model] response models
    origin = get_origin(response_model)
    if origin is list or origin is List:
        args = get_args(response_model)
        if args:
            item_model = args[0]
            if isinstance(data, list):
                return [convert_single_item(item, item_model) for item in data]
            else:
                # Single item but expected list
                return [convert_single_item(data, item_model)]
    
    # Handle single model
    if isinstance(data, list):
        return [convert_single_item(item, response_model) for item in data]
    else:
        return convert_single_item(data, response_model)


def convert_single_item(item: Any, target_model: Type[BaseModel]) -> BaseModel:
    """Convert a single item to the target model"""
    
    if item is None:
        return None
    
    # If it's already the correct type, return as-is
    if isinstance(item, target_model):
        return item
    
    # If it's a dict, use it directly
    if isinstance(item, dict):
        return create_response_instance(item, target_model)
    
    # If it's a SQLAlchemy model, convert it
    if hasattr(item, '__table__'):
        data_dict = sqlalchemy_to_dict(item)
        return create_response_instance(data_dict, target_model)
    
    # For other types, try to convert directly
    try:
        return target_model(**item.__dict__)
    except:
        # Last resort: try to create from item directly
        return target_model(item)


def sqlalchemy_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert SQLAlchemy model to dictionary with proper serialization"""
    result = {}
    
    # Get all columns from the SQLAlchemy model
    if hasattr(obj, '__table__'):
        for column in obj.__table__.columns:
            value = getattr(obj, column.name, None)
            result[column.name] = serialize_value(value)
    
    # Also get any additional attributes that might be needed
    for attr_name in dir(obj):
        if not attr_name.startswith('_') and attr_name not in result:
            try:
                value = getattr(obj, attr_name)
                if not callable(value) and not inspect.ismethod(value):
                    result[attr_name] = serialize_value(value)
            except:
                pass  # Skip attributes that can't be accessed
    
    return result


def serialize_value(value: Any) -> Any:
    """Serialize a value for JSON/Pydantic compatibility"""
    if value is None:
        return None
    
    # Handle enum values
    if isinstance(value, enum.Enum):
        return value.value
    
    # Handle datetime objects
    if isinstance(value, datetime):
        return value
    
    # Handle Decimal objects
    if isinstance(value, Decimal):
        return float(value)
    
    # Handle lists and nested objects
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    
    # Handle other special types
    if hasattr(value, 'isoformat'):  # Date/datetime objects
        return value
    
    return value


def create_response_instance(data: Dict[str, Any], target_model: Type[BaseModel]) -> BaseModel:
    """Create response model instance with smart field mapping"""
    
    # Get the model's fields
    model_fields = target_model.model_fields if hasattr(target_model, 'model_fields') else {}
    
    # Prepare the data for the model
    model_data = {}
    
    for field_name, field_info in model_fields.items():
        if field_name in data:
            # Direct mapping
            model_data[field_name] = data[field_name]
        else:
            # Try to infer or provide defaults
            model_data[field_name] = get_default_value_for_field(field_name, field_info, data)
    
    # Add any extra fields that might be needed
    for key, value in data.items():
        if key not in model_data:
            model_data[key] = value
    
    try:
        return target_model(**model_data)
    except Exception as e:
        logger.error(f"Failed to create {target_model.__name__} instance: {e}")
        logger.error(f"Data: {model_data}")
        raise


def get_default_value_for_field(field_name: str, field_info: Any, source_data: Dict[str, Any]) -> Any:
    """Get default value for a field that's not in source data"""
    
    # Common patterns for missing fields
    if field_name == 'eligible_sub_types':
        return source_data.get('sub_type_list', ['general'])
    
    if field_name in ['passed', 'warnings', 'errors']:
        return []
    
    if field_name == 'name_en':
        return source_data.get('name', '')
    
    # Try to get from field default
    if hasattr(field_info, 'default') and field_info.default is not None:
        return field_info.default
    
    # Type-based defaults
    field_type = getattr(field_info, 'annotation', None)
    if field_type:
        if field_type == list or get_origin(field_type) is list:
            return []
        elif field_type == dict:
            return {}
        elif field_type == str:
            return ""
        elif field_type == int:
            return 0
        elif field_type == bool:
            return False
    
    return None


# Enhanced decorator with validation
def auto_convert_and_validate(response_model: Type[BaseModel], validate_in_dev: bool = True):
    """
    Enhanced decorator that converts AND validates responses
    
    Args:
        response_model: Target Pydantic response model
        validate_in_dev: Whether to validate in development mode
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            if result is None:
                return result
            
            # Convert the result
            converted_result = convert_to_response_model(result, response_model)
            
            # Validate in development mode
            if validate_in_dev:
                from app.core.config import settings
                if settings.debug:
                    try:
                        # Ensure the conversion was successful by validating
                        if isinstance(converted_result, list):
                            for item in converted_result:
                                if not isinstance(item, response_model):
                                    raise ValueError(f"Conversion failed: expected {response_model}, got {type(item)}")
                        else:
                            if not isinstance(converted_result, response_model):
                                raise ValueError(f"Conversion failed: expected {response_model}, got {type(converted_result)}")
                        
                        logger.debug(f"✅ Auto-conversion and validation passed for {func.__name__}")
                        
                    except Exception as e:
                        logger.error(f"❌ Auto-conversion validation failed for {func.__name__}: {e}")
                        logger.error(f"Original result type: {type(result)}")
                        logger.error(f"Converted result type: {type(converted_result)}")
                        if settings.environment == "development":
                            raise
            
            return converted_result
        
        return wrapper
    return decorator


# Type hints for better IDE support
ResponseModelType = Type[BaseModel]
ConversionResult = Any


# Usage examples in docstring
USAGE_EXAMPLES = """
Usage Examples:

1. Basic auto-conversion:
   @router.get("/scholarships", response_model=List[ScholarshipResponse])
   @auto_convert_response(ScholarshipResponse)
   async def get_scholarships():
       scholarships = await db.query(Scholarship).all()
       return scholarships  # Automatically converted

2. With validation:
   @router.get("/scholarships", response_model=List[ScholarshipResponse])
   @auto_convert_and_validate(ScholarshipResponse)
   async def get_scholarships():
       scholarships = await db.query(Scholarship).all()
       return scholarships  # Converted and validated

3. Manual conversion:
   scholarships = await db.query(Scholarship).all()
   response = convert_to_response_model(scholarships, List[ScholarshipResponse])
   return response
"""