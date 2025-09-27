"""
Pydantic models for NYCU Employee API responses.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NYCUEmpItem(BaseModel):
    """Individual employee data item."""

    employee_no: str = Field(description="員工編號")
    employee_type: str = Field(description="員工類別")
    employee_name: str = Field(description="員工姓名")
    employee_ename: str = Field(description="員工英文姓名")
    zone_no: str = Field(description="校區代碼")
    zone_name: str = Field(description="校區名稱")
    dept_no: str = Field(description="系所代碼")
    dept_name: str = Field(description="系所名稱")
    service_dept_no: str = Field(description="服務系所代碼")
    service_dept_name: str = Field(description="服務系所名稱")
    class_no: str = Field(description="職級代碼")
    identity_no: str = Field(description="身分代碼")
    position_no: str = Field(description="職稱代碼")
    position_name: str = Field(description="職稱名稱")
    onboard_date: str = Field(description="到職日期")
    leave_date: str = Field(description="離職日期")
    email: str = Field(description="電子郵件")
    school_email: str = Field(description="學校電子郵件")
    mobile_phone: str = Field(description="手機號碼")
    employee_status: str = Field(description="員工狀態")
    update_time: str = Field(description="更新時間")


class NYCUEmpPage(BaseModel):
    """Employee API response with pagination."""

    status: str = Field(description="回應狀態碼")
    message: str = Field(description="回應訊息")
    total_page: int = Field(description="總頁數")
    total_count: int = Field(description="總筆數")
    empDataList: List[NYCUEmpItem] = Field(description="員工資料清單")

    @property
    def is_success(self) -> bool:
        """Check if the response indicates success."""
        return self.status == "0000"
