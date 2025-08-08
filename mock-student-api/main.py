"""
Mock Student Database API with HMAC-SHA256 Authentication

⚠️ DEVELOPMENT/TESTING ONLY ⚠️ 
Mock API for student database access during development.
DO NOT USE IN PRODUCTION.

Implements HMAC-SHA256 signature verification compatible with the university's
student information system API endpoints with in-memory data synchronized with init_db.
"""

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import os
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import logging
from auth import verify_hmac_signature, validate_request_params, STRICT_TIME_CHECK, STRICT_ENCODE_CHECK, MOCK_HMAC_KEY_HEX

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="校計中獎學金學生資料 Mock API",
    description="⚠️ 開發/測試專用 ⚠️ 模擬校計中 API，支援 HMAC-SHA256 驗簽，使用 in-memory 資料",
    version="2.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration (HMAC settings moved to auth.py)

# Request/Response Models
class StudentBasicRequest(BaseModel):
    account: str = Field(..., description="Account identifier")
    action: str = Field(..., description="Action identifier")
    stdcode: str = Field(..., description="Student code")

class StudentTermRequest(BaseModel):
    account: str = Field(..., description="Account identifier")
    action: str = Field(..., description="Action identifier")
    stdcode: str = Field(..., description="Student code")
    trmyear: str = Field(..., description="Academic year")
    trmterm: str = Field(..., description="Academic term")

class APIResponse(BaseModel):
    code: int
    msg: str
    data: List[Any]

# Mock Data按照你提供的實際API格式
SAMPLE_STUDENTS = {
    # 完全按照你提供的實際API格式
    "312551007": {
        "std_stdcode": "312551007",
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_highestschname": "國立陽明交通大學",
        "std_cname": "陳暐誠",
        "std_ename": "CHEN,WEI-CHENG",
        "std_pid": "S125472277",
        "std_bdate": "890912",
        "std_academyno": "C",
        "std_depno": "3551",
        "std_sex": "1",
        "std_nation": "中華民國",
        "std_degree": "2",
        "std_enrolltype": "4",
        "std_identity": "1",
        "std_schoolid": "1",
        "std_overseaplace": "",
        "std_termcount": "5",
        "std_studingstatus": "2",
        "mgd_title": "在學",
        "ToDoctor": "0",
        "com_commadd": "新竹市大學路1001號十三舍716室",
        "com_email": "jotp076315217@gmail.com",
        "com_cellphone": "0905169251"
    },
    
    # 其他測試學生，按照同樣格式
    "stu_under": {
        "std_stdcode": "stu_under",
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_highestschname": "台北市立建國高級中學",
        "std_cname": "學士生",
        "std_ename": "UNDERGRADUATE,STUDENT",
        "std_pid": "A123456789",
        "std_bdate": "920815",
        "std_academyno": "EE",
        "std_depno": "3551",
        "std_sex": "1",
        "std_nation": "中華民國",
        "std_degree": "3",
        "std_enrolltype": "1",
        "std_identity": "1",
        "std_schoolid": "1",
        "std_overseaplace": "",
        "std_termcount": "5",
        "std_studingstatus": "2",
        "mgd_title": "在學",
        "ToDoctor": "0",
        "com_commadd": "新竹市東區大學路1001號",
        "com_email": "stu_under@nycu.edu.tw",
        "com_cellphone": "0912345678"
    },
    
    "stu_phd": {
        "std_stdcode": "stu_phd",
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_highestschname": "國立交通大學",
        "std_cname": "博士生",
        "std_ename": "PHD,STUDENT",
        "std_pid": "B123456789",
        "std_bdate": "880310",
        "std_academyno": "EE",
        "std_depno": "3551",
        "std_sex": "1",
        "std_nation": "中華民國",
        "std_degree": "1",
        "std_enrolltype": "1",
        "std_identity": "1",
        "std_schoolid": "1",
        "std_overseaplace": "",
        "std_termcount": "5",
        "std_studingstatus": "2",
        "mgd_title": "在學",
        "ToDoctor": "0",
        "com_commadd": "新竹市東區大學路1001號",
        "com_email": "stu_phd@nycu.edu.tw",
        "com_cellphone": "0912345678"
    },
    
    "stu_master": {
        "std_stdcode": "stu_master",
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_highestschname": "國立台灣大學",
        "std_cname": "碩士生",
        "std_ename": "MASTER,STUDENT",
        "std_pid": "D123456789",
        "std_bdate": "900225",
        "std_academyno": "EE",
        "std_depno": "3551",
        "std_sex": "2",
        "std_nation": "中華民國",
        "std_degree": "2",
        "std_enrolltype": "1",
        "std_identity": "1",
        "std_schoolid": "1",
        "std_overseaplace": "",
        "std_termcount": "5",
        "std_studingstatus": "2",
        "mgd_title": "在學",
        "ToDoctor": "0",
        "com_commadd": "新竹市東區大學路1001號",
        "com_email": "stu_master@nycu.edu.tw",
        "com_cellphone": "0912345678"
    },
    
    "stu_direct": {
        "std_stdcode": "stu_direct",
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_highestschname": "國立清華大學",
        "std_cname": "李逕升",
        "std_ename": "LEE,DIRECT-PHD",
        "std_pid": "C123456789",
        "std_bdate": "910718",
        "std_academyno": "EE",
        "std_depno": "3551",
        "std_sex": "1",
        "std_nation": "中華民國",
        "std_degree": "1",  # 博士
        "std_enrolltype": "3",  # 逕讀博士
        "std_identity": "1",
        "std_schoolid": "1",
        "std_overseaplace": "",
        "std_termcount": "5",
        "std_studingstatus": "2",
        "mgd_title": "在學",
        "ToDoctor": "1",  # 逕讀博士
        "com_commadd": "新竹市東區大學路1001號",
        "com_email": "stu_direct@nycu.edu.tw",
        "com_cellphone": "0912345679"
    },
    
    "phd_china": {
        "std_stdcode": "phd_china",
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_highestschname": "北京大學",
        "std_cname": "陸生",
        "std_ename": "CHINA,STUDENT",
        "std_pid": "H123456789",
        "std_bdate": "870905",
        "std_academyno": "EE",
        "std_depno": "3551",
        "std_sex": "2",
        "std_nation": "中國大陸",
        "std_degree": "1",  # 博士
        "std_enrolltype": "1",
        "std_identity": "2",  # 陸生身份
        "std_schoolid": "1",
        "std_overseaplace": "中國大陸",
        "std_termcount": "5",
        "std_studingstatus": "2",
        "mgd_title": "在學",
        "ToDoctor": "0",
        "com_commadd": "新竹市東區大學路1001號國際學舍",
        "com_email": "phd_china@nycu.edu.tw",
        "com_cellphone": "0912345680"
    },
    
    "313612215": {
        "std_stdcode": "313612215",
        "std_enrollyear": "113",
        "std_enrollterm": "1",
        "std_highestschname": "逢甲大學",
        "std_cname": "陳弘穎",
        "std_ename": "CHEN,HUNG-YING",
        "std_pid": "S125410615",
        "std_bdate": "930412",
        "std_academyno": "I",
        "std_depno": "EECS01",
        "std_sex": "1",
        "std_nation": "中華民國",
        "std_degree": "3",
        "std_enrolltype": "1",
        "std_identity": "1",
        "std_schoolid": "1",
        "std_overseaplace": "",
        "std_termcount": "3",
        "std_studingstatus": "2",
        "mgd_title": "在學",
        "ToDoctor": "0",
        "com_commadd": "新竹市東區大學路100號",
        "com_email": "user@example.com",
        "com_cellphone": "0900000000"
    }
}

# 學期資料按照你提供的實際API格式
SAMPLE_TERMS = {
    "312551007": [
        {
            "std_stdcode": "312551007",
            "trm_year": "112",
            "trm_term": "1",
            "trm_termcount": "1",
            "trm_studystatus": "1",
            "trm_degree": "2",
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "3551",
            "trm_depname": "資科工碩",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.0"
        }
        ,
        {
            "std_stdcode": "312551007",
            "trm_year": "112",
            "trm_term": "2",
            "trm_termcount": "2",
            "trm_studystatus": "1",
            "trm_degree": "2",
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "3551",
            "trm_depname": "資科工碩",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.95"
        },
        {
            "std_stdcode": "312551007",
            "trm_year": "113",
            "trm_term": "1",
            "trm_termcount": "3",
            "trm_studystatus": "1",
            "trm_degree": "2",
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "3551",
            "trm_depname": "資科工碩",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.92"
        },
        {
            "std_stdcode": "312551007",
            "trm_year": "113",
            "trm_term": "2",
            "trm_termcount": "4",
            "trm_studystatus": "1",
            "trm_degree": "2",
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "3551",
            "trm_depname": "資科工碩",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.98"
        },
        {
            "std_stdcode": "312551007",
            "trm_year": "114",
            "trm_term": "1",
            "trm_termcount": "5",
            "trm_studystatus": "1",
            "trm_degree": "2",
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "3551",
            "trm_depname": "資科工碩",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.9"
        }
    ],
    "stu_under": [
        {
            "std_stdcode": "stu_under",
            "trm_year": "112",
            "trm_term": "1",
            "trm_termcount": "1",
            "trm_studystatus": "1",
            "trm_degree": "3",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機資訊學士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.5"
        }
        ,
        {
            "std_stdcode": "stu_under",
            "trm_year": "112",
            "trm_term": "2",
            "trm_termcount": "2",
            "trm_studystatus": "1",
            "trm_degree": "3",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機資訊學士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.55"
        },
        {
            "std_stdcode": "stu_under",
            "trm_year": "113",
            "trm_term": "1",
            "trm_termcount": "3",
            "trm_studystatus": "1",
            "trm_degree": "3",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機資訊學士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.6"
        },
        {
            "std_stdcode": "stu_under",
            "trm_year": "113",
            "trm_term": "2",
            "trm_termcount": "4",
            "trm_studystatus": "1",
            "trm_degree": "3",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機資訊學士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.65"
        },
        {
            "std_stdcode": "stu_under",
            "trm_year": "114",
            "trm_term": "1",
            "trm_termcount": "5",
            "trm_studystatus": "1",
            "trm_degree": "3",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機資訊學士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.6"
        }
    ],
    "stu_phd": [
        {
            "std_stdcode": "stu_phd",
            "trm_year": "112",
            "trm_term": "1",
            "trm_termcount": "1",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.1"
        }
        ,
        {
            "std_stdcode": "stu_phd",
            "trm_year": "112",
            "trm_term": "2",
            "trm_termcount": "2",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.05"
        },
        {
            "std_stdcode": "stu_phd",
            "trm_year": "113",
            "trm_term": "1",
            "trm_termcount": "3",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.15"
        },
        {
            "std_stdcode": "stu_phd",
            "trm_year": "113",
            "trm_term": "2",
            "trm_termcount": "4",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.2"
        },
        {
            "std_stdcode": "stu_phd",
            "trm_year": "114",
            "trm_term": "1",
            "trm_termcount": "5",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.2"
        }
    ],
    "stu_master": [
        {
            "std_stdcode": "stu_master",
            "trm_year": "112",
            "trm_term": "1",
            "trm_termcount": "1",
            "trm_studystatus": "1",
            "trm_degree": "2",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系碩士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.7"
        }
        ,
        {
            "std_stdcode": "stu_master",
            "trm_year": "112",
            "trm_term": "2",
            "trm_termcount": "2",
            "trm_studystatus": "1",
            "trm_degree": "2",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系碩士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.75"
        },
        {
            "std_stdcode": "stu_master",
            "trm_year": "113",
            "trm_term": "1",
            "trm_termcount": "3",
            "trm_studystatus": "1",
            "trm_degree": "2",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系碩士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.8"
        },
        {
            "std_stdcode": "stu_master",
            "trm_year": "113",
            "trm_term": "2",
            "trm_termcount": "4",
            "trm_studystatus": "1",
            "trm_degree": "2",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系碩士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.85"
        },
        {
            "std_stdcode": "stu_master",
            "trm_year": "114",
            "trm_term": "1",
            "trm_termcount": "5",
            "trm_studystatus": "1",
            "trm_degree": "2",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系碩士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.8"
        }
    ],
    "stu_direct": [
        {
            "std_stdcode": "stu_direct",
            "trm_year": "112",
            "trm_term": "1",
            "trm_termcount": "1",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.2"
        }
        ,
        {
            "std_stdcode": "stu_direct",
            "trm_year": "112",
            "trm_term": "2",
            "trm_termcount": "2",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.1"
        },
        {
            "std_stdcode": "stu_direct",
            "trm_year": "113",
            "trm_term": "1",
            "trm_termcount": "3",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.15"
        },
        {
            "std_stdcode": "stu_direct",
            "trm_year": "113",
            "trm_term": "2",
            "trm_termcount": "4",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.2"
        },
        {
            "std_stdcode": "stu_direct",
            "trm_year": "114",
            "trm_term": "1",
            "trm_termcount": "5",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.1"
        }
    ],
    "phd_china": [
        {
            "std_stdcode": "phd_china",
            "trm_year": "112",
            "trm_term": "1",
            "trm_termcount": "1",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.9"
        },
        {
            "std_stdcode": "phd_china",
            "trm_year": "112",
            "trm_term": "2",
            "trm_termcount": "2",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "4.0"
        },
        {
            "std_stdcode": "phd_china",
            "trm_year": "113",
            "trm_term": "1",
            "trm_termcount": "3",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.95"
        },
        {
            "std_stdcode": "phd_china",
            "trm_year": "113",
            "trm_term": "2",
            "trm_termcount": "4",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.98"
        },
        {
            "std_stdcode": "phd_china",
            "trm_year": "114",
            "trm_term": "1",
            "trm_termcount": "5",
            "trm_studystatus": "1",
            "trm_degree": "1",
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.95"
        }
    ],
    "313612215": [
        {
            "std_stdcode": "313612215",
            "trm_year": "113",
            "trm_term": "1",
            "trm_termcount": "1",
            "trm_studystatus": "1",
            "trm_degree": "3",
            "trm_academyno": "I",
            "trm_academyname": "智慧科學暨綠能學院",
            "trm_depno": "EECS01",
            "trm_depname": "電機資訊學士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.75"
        },
        {
            "std_stdcode": "313612215",
            "trm_year": "113",
            "trm_term": "2",
            "trm_termcount": "2",
            "trm_studystatus": "1",
            "trm_degree": "3",
            "trm_academyno": "I",
            "trm_academyname": "智慧科學暨綠能學院",
            "trm_depno": "EECS01",
            "trm_depname": "電機資訊學士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.8"
        },
        {
            "std_stdcode": "313612215",
            "trm_year": "114",
            "trm_term": "1",
            "trm_termcount": "3",
            "trm_studystatus": "1",
            "trm_degree": "3",
            "trm_academyno": "I",
            "trm_academyname": "智慧科學暨綠能學院",
            "trm_depno": "EECS01",
            "trm_depname": "電機資訊學士班",
            "trm_placings": "0",
            "trm_placingsrate": "0.0",
            "trm_depplacing": "0",
            "trm_depplacingrate": "0.0",
            "trm_ascore_gpa": "3.85"
        }
    ]
}

# HMAC verification function moved to auth.py

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "service": "校計中獎學金學生資料 Mock API",
        "warning": "⚠️ 開發/測試專用 - 請勿用於正式環境 ⚠️",
        "version": "2.1.0",
        "environment": "development",
        "data_source": "in-memory (matching real API format exactly)",
        "endpoints": {
            "student_basic": "POST /getsoaascholarshipstudent",
            "student_term": "POST /getsoaascholarshipstudentterm",
            "health": "GET /health"
        },
        "authentication": "HMAC-SHA256",
        "strict_mode": STRICT_TIME_CHECK,
        "available_students": list(SAMPLE_STUDENTS.keys()),
        "total_students_in_data": len(SAMPLE_STUDENTS)
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "mock-student-api",
        "version": "2.1.0",
        "data_source": "in-memory",
        "hmac_key_configured": bool(MOCK_HMAC_KEY_HEX),
        "strict_time_check": STRICT_TIME_CHECK,
        "strict_encode_check": STRICT_ENCODE_CHECK,
        "sample_students": len(SAMPLE_STUDENTS),
        "students_list": list(SAMPLE_STUDENTS.keys())
    }

@app.post("/getsoaascholarshipstudent")
async def get_student_basic_info(
    request: StudentBasicRequest,
    request_obj: Request,
    authorization: str = Header(..., description="HMAC-SHA256 authorization header"),
    content_type: str = Header(..., alias="content-type"),
    encode_type: Optional[str] = Header(None, alias="ENCODE_TYPE")
):
    """
    獲取獎學金學生基本資料 - 使用 in-memory 資料
    
    對應正式 API: POST /getsoaascholarshipstudent
    """
    try:
        request_body = await request_obj.body()
        request_json = request_body.decode('utf-8')
        
        if not verify_hmac_signature(authorization, request_json, content_type, encode_type):
            return JSONResponse(
                status_code=401,
                content={
                    "code": 401,
                    "msg": "HMAC signature verification failed",
                    "data": []
                }
            )
        
        # Validate request parameters
        validation_error = validate_request_params(request.account, request.action, "qrySoaaScholarshipStudent")
        if validation_error:
            return JSONResponse(status_code=400, content=validation_error)
        
        # Get student data from in-memory store
        student_data = SAMPLE_STUDENTS.get(request.stdcode)
        if not student_data:
            return JSONResponse(
                status_code=404,
                content={"code": 404, "msg": "Student not found", "data": []}
            )
        
        return {"code": 200, "msg": "success", "data": [student_data]}
        
    except Exception as e:
        logger.error(f"Error in get_student_basic_info: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"code": 500, "msg": "Internal server error", "data": []}
        )

@app.post("/getsoaascholarshipstudentterm")
async def get_student_term_info(
    request: StudentTermRequest,
    request_obj: Request,
    authorization: str = Header(..., description="HMAC-SHA256 authorization header"),
    content_type: str = Header(..., alias="content-type"),
    encode_type: Optional[str] = Header(None, alias="ENCODE_TYPE")
):
    """
    獲取獎學金學生學期資料 - 使用 in-memory 資料
    
    對應正式 API: POST /getsoaascholarshipstudentterm
    """
    try:
        request_body = await request_obj.body()
        request_json = request_body.decode('utf-8')
        
        if not verify_hmac_signature(authorization, request_json, content_type, encode_type):
            return JSONResponse(
                status_code=401,
                content={"code": 401, "msg": "HMAC signature verification failed", "data": []}
            )
        
        # Validate request parameters
        validation_error = validate_request_params(request.account, request.action, "qrySoaaScholarshipStudentTerm")
        if validation_error:
            return JSONResponse(status_code=400, content=validation_error)
        
        # Get student term data from in-memory store
        student_terms = SAMPLE_TERMS.get(request.stdcode, [])
        
        # Filter by year and term if specified
        filtered_terms = []
        for term in student_terms:
            if (term["trm_year"] == request.trmyear and 
                term["trm_term"] == request.trmterm):
                filtered_terms.append(term)
        
        if not filtered_terms:
            return JSONResponse(
                status_code=404,
                content={"code": 404, "msg": "Term data not found", "data": []}
            )
        
        return {"code": 200, "msg": "success", "data": filtered_terms}
        
    except Exception as e:
        logger.error(f"Error in get_student_term_info: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"code": 500, "msg": "Internal server error", "data": []}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)