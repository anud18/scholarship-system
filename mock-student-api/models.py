"""
Pydantic models for HMAC-SHA256 authenticated Mock Student Database API

⚠️ DEVELOPMENT/TESTING ONLY ⚠️
These models match the university's student information system API specification.
"""

from typing import Any, List

from pydantic import BaseModel, Field


# Request Models
class StudentBasicRequest(BaseModel):
    """Request model for getting student basic information"""

    account: str = Field(..., description="Account identifier (should be 'scholarship')")
    action: str = Field(..., description="Action identifier (should be 'qrySoaaScholarshipStudent')")
    stdcode: str = Field(..., description="Student code/number")


class StudentTermRequest(BaseModel):
    """Request model for getting student semester information"""

    account: str = Field(..., description="Account identifier (should be 'scholarship')")
    action: str = Field(..., description="Action identifier (should be 'qrySoaaScholarshipStudentTerm')")
    stdcode: str = Field(..., description="Student code/number")
    trmyear: str = Field(..., description="Academic year (e.g., '113')")
    trmterm: str = Field(..., description="Academic term (e.g., '1' or '2')")


# Response Data Models
class StudentBasicData(BaseModel):
    """Student basic information data model (matches actual SIS API)"""

    std_stdcode: str = Field(..., description="學號")
    std_enrollyear: int = Field(..., description="入學年度")
    std_enrollterm: int = Field(..., description="入學學期")
    std_highestschname: str = Field(..., description="原就讀系所/畢業學校")
    std_cname: str = Field(..., description="中文姓名")
    std_ename: str = Field(..., description="英文姓名")
    std_pid: str = Field(..., description="身分證字號")
    std_bdate: str = Field(..., description="生日 (格式: YYMMDD)")
    std_academyno: str = Field(..., description="學院代碼")
    std_depno: str = Field(..., description="系所代碼")
    std_sex: int = Field(..., description="性別 (1男 2女)")
    std_nation: str = Field(..., description="國籍")
    std_degree: int = Field(..., description="學位別 (1博士 2碩士 3大學)")
    std_enrolltype: int = Field(..., description="入學管道")
    std_identity: int = Field(..., description="身份別")
    std_schoolid: int = Field(..., description="在學身份")
    std_overseaplace: str = Field(..., description="僑居地")
    std_termcount: int = Field(..., description="在學學期數")
    std_studingstatus: int = Field(..., description="在學狀態")
    mgd_title: str = Field(..., description="學籍狀態中文")
    ToDoctor: int = Field(..., description="是否直升博士")
    com_commadd: str = Field(..., description="地址")
    com_email: str = Field(..., description="電子郵件")
    com_cellphone: str = Field(..., description="手機號碼")


class StudentTermData(BaseModel):
    """Student semester information data model (matches actual SIS API)"""

    std_stdcode: str = Field(..., description="學號")
    trm_year: int = Field(..., description="學年度")
    trm_term: int = Field(..., description="學期")
    trm_termcount: int = Field(..., description="修業學期數")
    trm_studystatus: int = Field(..., description="修業狀態")
    trm_degree: int = Field(..., description="學位別")
    trm_academyno: str = Field(..., description="學院代碼")
    trm_academyname: str = Field(..., description="學院名稱")
    trm_depno: str = Field(..., description="系所代碼")
    trm_depname: str = Field(..., description="系所名稱")
    trm_placings: int = Field(..., description="班排名")
    trm_placingsrate: float = Field(..., description="班排名百分比")
    trm_depplacing: int = Field(..., description="系排名")
    trm_depplacingrate: float = Field(..., description="系排名百分比")
    trm_ascore_gpa: float = Field(..., description="學期GPA")


# API Response Models
class APIResponse(BaseModel):
    """Standard API response format"""

    code: int = Field(..., description="Response code (200 for success)")
    msg: str = Field(..., description="Response message")
    data: List[Any] = Field(..., description="Response data array")


class StudentBasicResponse(APIResponse):
    """Response model for student basic information"""

    data: List[StudentBasicData]


class StudentTermResponse(APIResponse):
    """Response model for student semester information"""

    data: List[StudentTermData]


# Error Response Models
class ErrorResponse(BaseModel):
    """Error response model"""

    code: int = Field(..., description="Error code")
    msg: str = Field(..., description="Error message")
    data: List[Any] = Field(default_factory=list, description="Empty data array for errors")
