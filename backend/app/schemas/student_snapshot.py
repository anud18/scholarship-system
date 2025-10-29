"""
Student Snapshot Schema for Applications

Defines the structure of student_data JSON field in Application model.
student_data contains ONLY SIS API data snapshot (not student-submitted data).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class StudentSnapshotSchema(BaseModel):
    """
    Complete SIS API data snapshot at time of application submission.

    Contains data from two SIS APIs:
    1. ScholarshipStudent API - Basic student information
    2. ScholarshipStudentTerm API - Semester-specific data
    """

    # ===== API 1: ScholarshipStudent - 學生基本資料 =====
    std_stdcode: str = Field(..., description="學號")
    std_enrollyear: int = Field(..., description="入學年度 (民國年)")
    std_enrollterm: int = Field(..., description="入學學期")
    std_highestschname: Optional[str] = Field(None, description="最高學歷學校名稱")
    std_cname: str = Field(..., description="中文姓名")
    std_ename: Optional[str] = Field(None, description="英文姓名")
    std_pid: str = Field(..., description="身分證字號")
    std_bdate: Optional[str] = Field(None, description="生日 (格式: YYMMDD)")
    std_academyno: str = Field(..., description="學院代碼")
    std_depno: str = Field(..., description="系所代碼")
    std_sex: int = Field(..., description="性別 (1:男, 2:女)")
    std_nation: Optional[str] = Field(None, description="國籍")
    std_degree: int = Field(..., description="學位別")
    std_enrolltype: int = Field(..., description="入學方式")
    std_identity: int = Field(..., description="身分別")
    std_schoolid: int = Field(..., description="學校ID")
    std_overseaplace: Optional[str] = Field(None, description="僑居地")
    std_termcount: int = Field(..., description="目前學期數")
    std_studingstatus: int = Field(..., description="在學狀態")
    mgd_title: str = Field(..., description="學籍狀態中文")
    ToDoctor: Optional[int] = Field(None, description="是否直升博士")
    com_commadd: Optional[str] = Field(None, description="通訊地址")
    com_email: str = Field(..., description="Email")
    com_cellphone: Optional[str] = Field(None, description="手機號碼")

    # ===== API 2: ScholarshipStudentTerm - 學生學期資料 =====
    trm_year: int = Field(..., description="學期年度 (民國年)")
    trm_term: int = Field(..., description="學期別 (1:上學期, 2:下學期)")
    trm_termcount: int = Field(..., description="學期數 (第幾學期)")
    trm_studystatus: int = Field(..., description="修習狀態")
    trm_degree: int = Field(..., description="學位別")
    trm_academyno: str = Field(..., description="學院代碼")
    trm_academyname: str = Field(..., description="學院名稱")
    trm_depno: str = Field(..., description="系所代碼")
    trm_depname: str = Field(..., description="系所名稱")
    trm_placings: int = Field(..., description="班排名")
    trm_placingsrate: float = Field(..., description="班排名百分比")
    trm_depplacing: int = Field(..., description="系排名")
    trm_depplacingrate: float = Field(..., description="系排名百分比")
    trm_ascore_gpa: float = Field(..., description="GPA")

    # ===== Internal Metadata =====
    _api_fetched_at: Optional[datetime] = Field(None, description="API 資料取得時間")
    _term_data_status: Optional[str] = Field(None, description="學期資料狀態 (success/error/partial)")
    _term_error_message: Optional[str] = Field(None, description="學期資料錯誤訊息")

    class Config:
        json_schema_extra = {
            "example": {
                "std_stdcode": "310460031",
                "std_enrollyear": 110,
                "std_enrollterm": 1,
                "std_highestschname": "真理大學",
                "std_cname": "王小明",
                "std_ename": "Ming Wang",
                "std_pid": "TEST084302",
                "std_bdate": "700101",
                "std_academyno": "A",
                "std_depno": "4460",
                "std_sex": 2,
                "std_nation": "中華民國",
                "std_degree": 1,
                "std_enrolltype": 9,
                "std_identity": 1,
                "std_schoolid": 1,
                "std_overseaplace": "",
                "std_termcount": 5,
                "std_studingstatus": 1,
                "mgd_title": "在學",
                "ToDoctor": 1,
                "com_commadd": "新竹市東區大學路1001號",
                "com_email": "nctutest@g2.nctu.edu.tw",
                "com_cellphone": "",
                "trm_year": 114,
                "trm_term": 1,
                "trm_termcount": 5,
                "trm_studystatus": 1,
                "trm_degree": 1,
                "trm_academyno": "A",
                "trm_academyname": "人社院",
                "trm_depno": "4460",
                "trm_depname": "教育博",
                "trm_placings": 0,
                "trm_placingsrate": 0.0,
                "trm_depplacing": 0,
                "trm_depplacingrate": 0.0,
                "trm_ascore_gpa": 0.0,
                "_api_fetched_at": "2025-10-22T17:27:08Z",
                "_term_data_status": "success",
            }
        }


class StudentSnapshotMinimal(BaseModel):
    """
    Minimal student data for quick validation.
    Used when full snapshot is not available.
    """

    std_stdcode: str
    std_cname: str
    com_email: str

    class Config:
        json_schema_extra = {
            "example": {"std_stdcode": "310460031", "std_cname": "王小明", "com_email": "nctutest@g2.nctu.edu.tw"}
        }
