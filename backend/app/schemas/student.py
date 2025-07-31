"""
Student schemas for API requests and responses with normalized database design
"""

from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


# === 查詢表相關 Schemas ===

class DegreeBase(BaseModel):
    """學位基礎 schema"""
    name: str = Field(..., description="學位名稱")

class DegreeResponse(DegreeBase):
    """學位回應 schema"""
    id: int
    
    class Config:
        from_attributes = True


class IdentityBase(BaseModel):
    """身份基礎 schema"""
    name: str = Field(..., description="身份名稱")

class IdentityResponse(IdentityBase):
    """身份回應 schema"""
    id: int
    
    class Config:
        from_attributes = True


class StudyingStatusBase(BaseModel):
    """學籍狀態基礎 schema"""
    name: str = Field(..., description="狀態名稱")

class StudyingStatusResponse(StudyingStatusBase):
    """學籍狀態回應 schema"""
    id: int
    
    class Config:
        from_attributes = True


class SchoolIdentityBase(BaseModel):
    """學校身份基礎 schema"""
    name: str = Field(..., description="學校身份名稱")

class SchoolIdentityResponse(SchoolIdentityBase):
    """學校身份回應 schema"""
    id: int
    
    class Config:
        from_attributes = True


class AcademyBase(BaseModel):
    """學院基礎 schema"""
    code: Optional[str] = Field(None, description="學院代碼")
    name: str = Field(..., description="學院名稱")

class AcademyCreate(AcademyBase):
    """學院建立 schema"""
    pass

class AcademyResponse(AcademyBase):
    """學院回應 schema"""
    id: int
    
    class Config:
        from_attributes = True


class DepartmentBase(BaseModel):
    """系所基礎 schema"""
    code: Optional[str] = Field(None, description="系所代碼")
    name: str = Field(..., description="系所名稱")

class DepartmentCreate(DepartmentBase):
    """系所建立 schema"""
    pass

class DepartmentResponse(DepartmentBase):
    """系所回應 schema"""
    id: int
    
    class Config:
        from_attributes = True


class EnrollTypeBase(BaseModel):
    """入學管道基礎 schema"""
    code: Optional[str] = Field(None, description="入學管道代碼")
    name: str = Field(..., description="入學管道名稱")
    degreeId: int = Field(..., description="學位ID")

class EnrollTypeCreate(EnrollTypeBase):
    """入學管道建立 schema"""
    pass

class EnrollTypeResponse(EnrollTypeBase):
    """入學管道回應 schema"""
    id: int
    degree: Optional[DegreeResponse] = None
    
    class Config:
        from_attributes = True


# === 學生資料相關 Schemas ===

class StudentBase(BaseModel):
    """學生基礎 schema - 更新版本"""
    # 學籍資料
    std_stdno: Optional[str] = Field(None, description="學號代碼")
    std_stdcode: str = Field(..., description="學號 (nycu_id)")
    std_pid: Optional[str] = Field(None, description="身分證字號")
    std_cname: str = Field(..., description="中文姓名")
    std_ename: str = Field(..., description="英文姓名")
    std_degree: str = Field(..., description="攻讀學位：1:博士, 2:碩士, 3:學士")
    std_studingstatus: Optional[str] = Field(None, description="在學狀態")
    std_sex: Optional[str] = Field(None, description="性別: 1:男, 2:女")
    std_enrollyear: Optional[str] = Field(None, description="入學學年度 (民國年)")
    std_enrollterm: Optional[str] = Field(None, description="入學學期 (第一或第二)")
    std_termcount: Optional[int] = Field(None, description="在學學期數")

    # 國籍與身份
    std_nation: Optional[str] = Field(None, description="1: 中華民國 2: 其他")
    std_schoolid: Optional[str] = Field(None, description="在學身份 (數字代碼)")
    std_identity: Optional[str] = Field(None, description="陸生、僑生、外籍生等")

    # 系所與學院
    std_depno: Optional[str] = Field(None, description="系所代碼")
    std_depname: Optional[str] = Field(None, description="系所名稱")
    std_aca_no: Optional[str] = Field(None, description="學院代碼")
    std_aca_cname: Optional[str] = Field(None, description="學院名稱")

    # 學歷背景
    std_highestschname: Optional[str] = Field(None, description="原就讀系所／畢業學校")
    
    # 聯絡資訊
    com_cellphone: Optional[str] = Field(None, description="手機號碼")
    com_email: Optional[str] = Field(None, description="電子郵件")
    com_commzip: Optional[str] = Field(None, description="郵遞區號")
    com_commadd: Optional[str] = Field(None, description="地址")

    # 入學日期
    std_enrolled_date: Optional[date] = Field(None, description="入學日期")

    # 匯款資訊
    std_bank_account: Optional[str] = Field(None, description="銀行帳號")

    # 其他備註
    notes: Optional[str] = Field(None, description="備註")

class StudentCreate(StudentBase):
    """學生建立 schema"""
    pass

class StudentUpdate(BaseModel):
    """學生更新 schema"""
    std_stdno: Optional[str] = None
    std_pid: Optional[str] = None
    std_cname: Optional[str] = None
    std_ename: Optional[str] = None
    std_degree: Optional[str] = None
    std_studingstatus: Optional[str] = None
    std_sex: Optional[str] = None
    std_enrollyear: Optional[str] = None
    std_enrollterm: Optional[str] = None
    std_termcount: Optional[int] = None
    std_nation: Optional[str] = None
    std_schoolid: Optional[str] = None
    std_identity: Optional[str] = None
    std_depno: Optional[str] = None
    std_depname: Optional[str] = None
    std_aca_no: Optional[str] = None
    std_aca_cname: Optional[str] = None
    std_highestschname: Optional[str] = None
    com_cellphone: Optional[str] = None
    com_email: Optional[str] = None
    com_commzip: Optional[str] = None
    com_commadd: Optional[str] = None
    std_enrolled_date: Optional[date] = None
    std_bank_account: Optional[str] = None
    notes: Optional[str] = None

class StudentResponse(StudentBase):
    """學生回應 schema"""
    id: int
    
    @property
    def displayName(self) -> str:
        """取得顯示名稱"""
        return str(self.std_cname or self.std_ename or self.std_stdcode or "")
    
    def get_student_type(self) -> str:
        """取得學生類型"""
        if self.std_degree == "1":
            return "phd"
        elif self.std_degree == "2":
            return "master"
        else:
            return "undergraduate"
    
    class Config:
        from_attributes = True


class StudentDetailResponse(StudentResponse):
    """學生詳細資料回應 schema"""
    pass


class StudentSearchParams(BaseModel):
    """學生查詢參數 schema"""
    std_stdcode: Optional[str] = None
    std_cname: Optional[str] = None
    std_ename: Optional[str] = None
    std_degree: Optional[str] = None
    std_aca_no: Optional[str] = None
    std_depno: Optional[str] = None
    std_studingstatus: Optional[str] = None
    std_enrollyear: Optional[str] = None
    
    # 分頁參數
    page: int = Field(1, ge=1, description="頁碼")
    size: int = Field(20, ge=1, le=100, description="每頁筆數") 