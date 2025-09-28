"""
Base interface for NYCU Employee API clients.
"""

from abc import ABC, abstractmethod
from typing import List

from .models import NYCUEmpPage


class NYCUEmpClientBase(ABC):
    """Base interface for all NYCU Employee API clients."""

    @abstractmethod
    async def get_employee_page(self, page_row: str = "1", status: str = "01") -> NYCUEmpPage:
        """
        Get a page of employee data.

        Args:
            page_row: Page number as string (default: "1")
            status: Employee status filter as string (default: "01")

        Returns:
            NYCUEmpPage: Page of employee data with metadata

        Raises:
            NYCUEmpError: When API request fails
        """
        pass

    async def get_all_employees(self, status: str = "01") -> List[NYCUEmpPage]:
        """
        Get all employee data by automatically paginating through all pages.

        Args:
            status: Employee status filter as string (default: "01")

        Returns:
            List[NYCUEmpPage]: All pages of employee data

        Raises:
            NYCUEmpError: When API request fails
        """
        all_pages = []
        page = 1

        while True:
            page_data = await self.get_employee_page(page_row=str(page), status=status)
            all_pages.append(page_data)

            # Stop if this is the last page
            if page >= page_data.total_page:
                break

            page += 1

        return all_pages
