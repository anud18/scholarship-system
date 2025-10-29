"""
Standard API response schemas following the project patterns
"""

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel

DataType = TypeVar("DataType")


class ApiResponse(BaseModel, Generic[DataType]):
    """Standard API response format"""

    success: bool
    message: str
    data: Optional[DataType] = None
    errors: Optional[List[str]] = None
    trace_id: Optional[str] = None

    class Config:
        """Pydantic configuration"""

        from_attributes = True


class ValidationError(BaseModel):
    """Validation error detail"""

    field: str
    message: str
    code: Optional[str] = None


class DetailedApiResponse(BaseModel, Generic[DataType]):
    """Detailed API response with validation errors"""

    success: bool
    message: str
    data: Optional[DataType] = None
    errors: Optional[List[str]] = None
    validation_errors: Optional[List[ValidationError]] = None
    trace_id: Optional[str] = None

    class Config:
        """Pydantic configuration"""

        from_attributes = True


class PaginatedApiResponse(BaseModel, Generic[DataType]):
    """Paginated API response"""

    success: bool
    message: str
    data: Optional[List[DataType]] = None
    total: Optional[int] = None
    page: Optional[int] = None
    size: Optional[int] = None
    pages: Optional[int] = None
    errors: Optional[List[str]] = None
    trace_id: Optional[str] = None

    class Config:
        """Pydantic configuration"""

        from_attributes = True
