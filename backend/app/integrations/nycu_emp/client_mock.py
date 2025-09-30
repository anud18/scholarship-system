"""
Mock client for NYCU Employee API (development use only).
"""

import logging
from typing import List

from .client_base import NYCUEmpClientBase
from .models import NYCUEmpItem, NYCUEmpPage

logger = logging.getLogger(__name__)


class NYCUEmpMockClient(NYCUEmpClientBase):
    """Mock client for NYCU Employee API development testing."""

    def __init__(self):
        """Initialize mock client."""
        logger.info("NYCUEmpMockClient initialized (development mode)")

    def _get_sample_employees(self, status: str = "01") -> List[NYCUEmpItem]:
        """
        Get sample employee data based on status.

        Args:
            status: Employee status filter

        Returns:
            List of sample employee items
        """
        base_employees = [
            {
                "employee_no": "A00001",
                "employee_type": "E",
                "employee_name": "黃OO",
                "employee_ename": "HUANG,OO",
                "zone_no": "H01",
                "zone_name": "光復校區",
                "dept_no": "A307",
                "dept_name": "光電工程學系",
                "service_dept_no": "A307",
                "service_dept_name": "光電工程學系",
                "class_no": "A",
                "identity_no": "A01",
                "position_no": "A01004",
                "position_name": "助理教授",
                "onboard_date": "2021-02-01",
                "leave_date": "1900-01-01",
                "email": "huang.oo@nycu.edu.tw",
                "school_email": "huang.oo@nycu.edu.tw",
                "mobile_phone": "0912345678",
                "employee_status": "01",
                "update_time": "2025-09-17 10:23:28.360",
            },
            {
                "employee_no": "A00002",
                "employee_type": "E",
                "employee_name": "李OO",
                "employee_ename": "LEE,OO",
                "zone_no": "H01",
                "zone_name": "光復校區",
                "dept_no": "A301",
                "dept_name": "電機工程學系",
                "service_dept_no": "A301",
                "service_dept_name": "電機工程學系",
                "class_no": "A",
                "identity_no": "A01",
                "position_no": "A01005",
                "position_name": "副教授",
                "onboard_date": "2019-08-01",
                "leave_date": "1900-01-01",
                "email": "lee.oo@nycu.edu.tw",
                "school_email": "lee.oo@nycu.edu.tw",
                "mobile_phone": "0987654321",
                "employee_status": "01",
                "update_time": "2025-09-17 10:23:28.360",
            },
            {
                "employee_no": "A00003",
                "employee_type": "E",
                "employee_name": "陳OO",
                "employee_ename": "CHEN,OO",
                "zone_no": "B01",
                "zone_name": "博愛校區",
                "dept_no": "B201",
                "dept_name": "資訊工程學系",
                "service_dept_no": "B201",
                "service_dept_name": "資訊工程學系",
                "class_no": "A",
                "identity_no": "A01",
                "position_no": "A01006",
                "position_name": "教授",
                "onboard_date": "2015-02-01",
                "leave_date": "1900-01-01",
                "email": "chen.oo@nycu.edu.tw",
                "school_email": "chen.oo@nycu.edu.tw",
                "mobile_phone": "0955123456",
                "employee_status": "01",
                "update_time": "2025-09-17 10:23:28.360",
            },
            {
                "employee_no": "A00004",
                "employee_type": "S",
                "employee_name": "張OO",
                "employee_ename": "CHANG,OO",
                "zone_no": "H01",
                "zone_name": "光復校區",
                "dept_no": "A101",
                "dept_name": "行政單位",
                "service_dept_no": "A101",
                "service_dept_name": "學務處",
                "class_no": "B",
                "identity_no": "B02",
                "position_no": "B02001",
                "position_name": "組長",
                "onboard_date": "2020-03-01",
                "leave_date": "2023-12-31",
                "email": "chang.oo@nycu.edu.tw",
                "school_email": "chang.oo@nycu.edu.tw",
                "mobile_phone": "0933456789",
                "employee_status": "02",
                "update_time": "2025-09-17 10:23:28.360",
            },
        ]

        # Filter by status
        if status == "01":
            # Active employees
            filtered = [emp for emp in base_employees if emp["employee_status"] == "01"]
        elif status == "02":
            # Inactive employees
            filtered = [emp for emp in base_employees if emp["employee_status"] == "02"]
        else:
            # All employees
            filtered = base_employees

        return [NYCUEmpItem(**emp) for emp in filtered]

    async def get_employee_page(self, page_row: str = "1", status: str = "01") -> NYCUEmpPage:
        """
        Get mock employee data page.

        Args:
            page_row: Page number as string
            status: Employee status filter as string

        Returns:
            NYCUEmpPage: Mock employee data with pagination
        """
        logger.info(f"Mock request: page_row={page_row}, status={status}")

        # Get sample data
        all_employees = self._get_sample_employees(status)

        # Simulate pagination (2 employees per page)
        page_size = 2
        page_num = int(page_row)
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size

        page_employees = all_employees[start_idx:end_idx]
        total_count = len(all_employees)
        total_pages = (total_count + page_size - 1) // page_size  # Ceiling division

        # Return mock response
        return NYCUEmpPage(
            status="0000",
            message="",
            total_page=total_pages,
            total_count=total_count,
            empDataList=page_employees,
        )
