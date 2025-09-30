"""
NYCU Employee API endpoints.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.integrations.nycu_emp import (
    NYCUEmpAuthenticationError,
    NYCUEmpConnectionError,
    NYCUEmpError,
    NYCUEmpItem,
    NYCUEmpTimeoutError,
    NYCUEmpValidationError,
    create_nycu_emp_client_from_env,
)

router = APIRouter()


class EmployeeListResponse(BaseModel):
    """Response model for employee list."""

    status: str
    message: str
    total_page: int
    total_count: int
    employees: List[NYCUEmpItem]
    page: int


class EmployeeSearchResponse(BaseModel):
    """Response model for employee search."""

    employees: List[NYCUEmpItem]
    total_count: int
    filtered_count: int


@router.get("employees", response_model=EmployeeListResponse)
async def get_employees(
    page: int = Query(1, ge=1, description="Page number (starting from 1)"),
    status: str = Query("01", description="Employee status filter (01=active, 02=inactive)"),
):
    """
    Get paginated list of NYCU employees.

    Args:
        page: Page number (starting from 1)
        status: Employee status filter ("01" for active, "02" for inactive)

    Returns:
        EmployeeListResponse: Paginated employee data

    Raises:
        HTTPException: When API request fails
    """
    try:
        # Create client based on environment
        client = create_nycu_emp_client_from_env()

        # Use context manager for HTTP client if needed
        if hasattr(client, "__aenter__"):
            async with client as c:
                result = await c.get_employee_page(page_row=str(page), status=status)
        else:
            result = await client.get_employee_page(page_row=str(page), status=status)

        return EmployeeListResponse(
            status=result.status,
            message=result.message,
            total_page=result.total_page,
            total_count=result.total_count,
            employees=result.empDataList,
            page=page,
        )

    except NYCUEmpAuthenticationError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
    except NYCUEmpValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
    except NYCUEmpConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")
    except NYCUEmpTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Request timeout: {str(e)}")
    except NYCUEmpError as e:
        raise HTTPException(status_code=500, detail=f"API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("employees/all", response_model=List[EmployeeListResponse])
async def get_all_employees(
    status: str = Query("01", description="Employee status filter (01=active, 02=inactive)"),
):
    """
    Get all NYCU employees by automatically paginating through all pages.

    Args:
        status: Employee status filter ("01" for active, "02" for inactive)

    Returns:
        List[EmployeeListResponse]: All pages of employee data

    Raises:
        HTTPException: When API request fails
    """
    try:
        # Create client based on environment
        client = create_nycu_emp_client_from_env()

        # Use context manager for HTTP client if needed
        if hasattr(client, "__aenter__"):
            async with client as c:
                pages = await c.get_all_employees(status=status)
        else:
            pages = await client.get_all_employees(status=status)

        # Convert to response format
        response_pages = []
        for i, page in enumerate(pages, 1):
            response_pages.append(
                EmployeeListResponse(
                    status=page.status,
                    message=page.message,
                    total_page=page.total_page,
                    total_count=page.total_count,
                    employees=page.empDataList,
                    page=i,
                )
            )

        return response_pages

    except NYCUEmpAuthenticationError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
    except NYCUEmpValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
    except NYCUEmpConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")
    except NYCUEmpTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Request timeout: {str(e)}")
    except NYCUEmpError as e:
        raise HTTPException(status_code=500, detail=f"API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("employees/search", response_model=EmployeeSearchResponse)
async def search_employees(
    query: Optional[str] = Query(None, description="Search query for employee name or ID"),
    dept_name: Optional[str] = Query(None, description="Department name filter"),
    position_name: Optional[str] = Query(None, description="Position name filter"),
    status: str = Query("01", description="Employee status filter (01=active, 02=inactive)"),
):
    """
    Search NYCU employees with various filters.

    Args:
        query: Search query for employee name or ID
        dept_name: Department name filter
        position_name: Position name filter
        status: Employee status filter ("01" for active, "02" for inactive)

    Returns:
        EmployeeSearchResponse: Filtered employee search results

    Raises:
        HTTPException: When API request fails
    """
    try:
        # Create client based on environment
        client = create_nycu_emp_client_from_env()

        # Get all employees first
        if hasattr(client, "__aenter__"):
            async with client as c:
                pages = await c.get_all_employees(status=status)
        else:
            pages = await client.get_all_employees(status=status)

        # Combine all employees from all pages
        all_employees = []
        total_count = 0
        for page in pages:
            all_employees.extend(page.empDataList)
            total_count = page.total_count  # Same for all pages

        # Apply filters
        filtered_employees = all_employees

        if query:
            query_lower = query.lower()
            filtered_employees = [
                emp
                for emp in filtered_employees
                if (
                    query_lower in emp.employee_name.lower()
                    or query_lower in emp.employee_ename.lower()
                    or query_lower in emp.employee_no.lower()
                )
            ]

        if dept_name:
            dept_lower = dept_name.lower()
            filtered_employees = [emp for emp in filtered_employees if dept_lower in emp.dept_name.lower()]

        if position_name:
            position_lower = position_name.lower()
            filtered_employees = [emp for emp in filtered_employees if position_lower in emp.position_name.lower()]

        return EmployeeSearchResponse(
            employees=filtered_employees,
            total_count=total_count,
            filtered_count=len(filtered_employees),
        )

    except NYCUEmpAuthenticationError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
    except NYCUEmpValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
    except NYCUEmpConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")
    except NYCUEmpTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Request timeout: {str(e)}")
    except NYCUEmpError as e:
        raise HTTPException(status_code=500, detail=f"API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/employees/{employee_no}", response_model=Optional[NYCUEmpItem])
async def get_employee_by_no(
    employee_no: str,
    status: str = Query("01", description="Employee status filter (01=active, 02=inactive)"),
):
    """
    Get specific employee by employee number.

    Args:
        employee_no: Employee number to search for
        status: Employee status filter ("01" for active, "02" for inactive)

    Returns:
        Optional[NYCUEmpItem]: Employee data if found, None otherwise

    Raises:
        HTTPException: When API request fails
    """
    try:
        # Create client based on environment
        client = create_nycu_emp_client_from_env()

        # Get all employees and search for the specific one
        if hasattr(client, "__aenter__"):
            async with client as c:
                pages = await c.get_all_employees(status=status)
        else:
            pages = await client.get_all_employees(status=status)

        # Search for employee across all pages
        for page in pages:
            for employee in page.empDataList:
                if employee.employee_no == employee_no:
                    return employee

        # Employee not found
        raise HTTPException(status_code=404, detail=f"Employee {employee_no} not found")

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except NYCUEmpAuthenticationError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
    except NYCUEmpValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
    except NYCUEmpConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")
    except NYCUEmpTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Request timeout: {str(e)}")
    except NYCUEmpError as e:
        raise HTTPException(status_code=500, detail=f"API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
