"""
Pydantic models for HMAC-SHA256 authenticated Mock Student Database API

⚠️ DEVELOPMENT/TESTING ONLY ⚠️ 
These models match the university's student information system API specification.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Any


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
    """Student basic information data model"""
    std_stdno: str = Field(..., description="學號代碼")
    std_stdcode: str = Field(..., description="學號")
    std_pid: str = Field(..., description="身分證字號")
    std_cname: str = Field(..., description="中文姓名")
    std_ename: str = Field(..., description="英文姓名")
    std_degree: str = Field(..., description="學位別 (1博士 2碩士 3大學)")
    std_studingstatus: str = Field(..., description="在學狀態")
    std_nation: str = Field(..., description="國籍")
    std_schoolid: str = Field(..., description="在學身份")
    std_identity: str = Field(..., description="身份別")
    std_termcount: str = Field(..., description="在學學期數")
    std_depno: str = Field(..., description="系所代碼")
    dep_depname: str = Field(..., description="系所名稱")
    std_academyno: str = Field(..., description="學院代碼")
    aca_cname: str = Field(..., description="學院中文名")
    std_enrolltype: str = Field(..., description="入學管道")
    std_directmemo: str = Field(..., description="逕博註記")
    std_highestschname: str = Field(..., description="原就讀系所/畢業學校")
    com_cellphone: str = Field(..., description="手機號碼")
    com_email: str = Field(..., description="電子郵件")
    com_commzip: str = Field(..., description="郵遞區號")
    com_commadd: str = Field(..., description="地址")
    std_sex: str = Field(..., description="性別 (1男 2女)")
    std_enrollyear: str = Field(..., description="入學年度")
    std_enrollterm: str = Field(..., description="入學學期")
    std_enrolldate: str = Field(..., description="入學日期")


class StudentTermData(BaseModel):
    """Student semester information data model"""
    trm_year: str = Field(..., description="學年度")
    trm_term: str = Field(..., description="學期")
    trm_stdno: str = Field(..., description="學號")
    trm_studystatus: str = Field(..., description="修業狀態")
    trm_ascore: str = Field(..., description="學期平均成績")
    trm_termcount: str = Field(..., description="修業學期數")
    trm_grade: str = Field(..., description="年級")
    trm_degree: str = Field(..., description="學位別")
    trm_academyname: str = Field(..., description="學院名稱")
    trm_depname: str = Field(..., description="系所名稱")
    trm_ascore_gpa: str = Field(..., description="學期GPA")
    trm_stdascore: str = Field(..., description="累積平均成績")
    trm_placingsrate: str = Field(..., description="班排名百分比")
    trm_depplacingrate: str = Field(..., description="系排名百分比")


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