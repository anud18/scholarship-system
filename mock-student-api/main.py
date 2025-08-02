"""
Mock Student Database API with HMAC-SHA256 Authentication

⚠️ DEVELOPMENT/TESTING ONLY ⚠️ 
Mock API for student database access during development.
DO NOT USE IN PRODUCTION.

Implements HMAC-SHA256 signature verification compatible with the university's
student information system API endpoints.
"""

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="校計中獎學金學生資料 Mock API",
    description="⚠️ 開發/測試專用 ⚠️ 模擬校計中 API，支援 HMAC-SHA256 驗簽",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
MOCK_HMAC_KEY_HEX = os.getenv("MOCK_HMAC_KEY_HEX", "4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a")
STRICT_TIME_CHECK = os.getenv("STRICT_TIME_CHECK", "true").lower() == "true"
STRICT_ENCODE_CHECK = os.getenv("STRICT_ENCODE_CHECK", "false").lower() == "true"
TIME_TOLERANCE_MINUTES = int(os.getenv("TIME_TOLERANCE_MINUTES", "5"))

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

class StudentBasicData(BaseModel):
    std_stdno: str
    std_stdcode: str
    std_pid: str
    std_cname: str
    std_ename: str
    std_degree: str
    std_studingstatus: str
    std_nation: str
    std_schoolid: str
    std_identity: str
    std_termcount: str
    std_depno: str
    dep_depname: str
    std_academyno: str
    aca_cname: str
    std_enrolltype: str
    std_directmemo: str
    std_highestschname: str
    com_cellphone: str
    com_email: str
    com_commzip: str
    com_commadd: str
    std_sex: str
    std_enrollyear: str
    std_enrollterm: str
    std_enrolldate: str

class StudentTermData(BaseModel):
    trm_year: str
    trm_term: str
    trm_stdno: str
    trm_studystatus: str
    trm_ascore: str
    trm_termcount: str
    trm_grade: str
    trm_degree: str
    trm_academyname: str
    trm_depname: str
    trm_ascore_gpa: str
    trm_stdascore: str
    trm_placingsrate: str
    trm_depplacingrate: str

class APIResponse(BaseModel):
    code: int
    msg: str
    data: List[Any]

# Mock Data
SAMPLE_STUDENTS = {
    "313612215": {
        "std_stdno": "A123456789",
        "std_stdcode": "313612215",
        "std_pid": "S125410615",
        "std_cname": "陳弘穎",
        "std_ename": "CHEN,HUNG-YING",
        "std_degree": "3",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "1",
        "std_termcount": "3",
        "std_depno": "EECS01",
        "dep_depname": "電機工程學系",
        "std_academyno": "I",
        "aca_cname": "工學院",
        "std_enrolltype": "1",
        "std_directmemo": "",
        "std_highestschname": "逢甲大學",
        "com_cellphone": "0900000000",
        "com_email": "user@example.com",
        "com_commzip": "300",
        "com_commadd": "新竹市東區大學路100號",
        "std_sex": "1",
        "std_enrollyear": "113",
        "std_enrollterm": "1",
        "std_enrolldate": "2024-09"
    },
    "123456789": {
        "std_stdno": "B987654321",
        "std_stdcode": "123456789",
        "std_pid": "A123456789",
        "std_cname": "李美麗",
        "std_ename": "LEE,MEI-LI",
        "std_degree": "2",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "2",
        "std_termcount": "4",
        "std_depno": "CS01",
        "dep_depname": "資訊工程學系",
        "std_academyno": "C",
        "aca_cname": "資訊學院",
        "std_enrolltype": "4",
        "std_directmemo": "",
        "std_highestschname": "台灣大學",
        "com_cellphone": "0912345678",
        "com_email": "student@example.com",
        "com_commzip": "300",
        "com_commadd": "新竹市東區大學路101號",
        "std_sex": "2",
        "std_enrollyear": "112",
        "std_enrollterm": "2",
        "std_enrolldate": "2024-02"
    },
    # PhD Students - Comprehensive Scenarios Based on init_db Rules
    
    # Regular PhD Students - Various Enrollment Types
    "D11142001": {
        "std_stdno": "D111420010",
        "std_stdcode": "D11142001",
        "std_pid": "F223344556",
        "std_cname": "王志明",
        "std_ename": "WANG,CHIH-MING",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "1",
        "std_termcount": "7",
        "std_depno": "EECS02",
        "dep_depname": "電機工程學系",
        "std_academyno": "I",
        "aca_cname": "工學院",
        "std_enrolltype": "1",
        "std_directmemo": "",
        "std_highestschname": "清華大學電機工程學系",
        "com_cellphone": "0987654321",
        "com_email": "wang.phd@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區清華路二段101號",
        "std_sex": "1",
        "std_enrollyear": "111",
        "std_enrollterm": "1",
        "std_enrolldate": "2022-09"
    },
    "D11042002": {
        "std_stdno": "D110420020",
        "std_stdcode": "D11042002",
        "std_pid": "G334455667",
        "std_cname": "林雅婷",
        "std_ename": "LIN,YA-TING",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "2",
        "std_termcount": "9",
        "std_depno": "CS02",
        "dep_depname": "資訊工程學系",
        "std_academyno": "C",
        "aca_cname": "資訊學院",
        "std_enrolltype": "8",
        "std_directmemo": "大學逕博",
        "std_highestschname": "清華大學資訊工程學系",
        "com_cellphone": "0955123456",
        "com_email": "lin.cs@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區光復路二段101號",
        "std_sex": "2",
        "std_enrollyear": "110",
        "std_enrollterm": "1",
        "std_enrolldate": "2021-09"
    },
    "D10942003": {
        "std_stdno": "D109420030",
        "std_stdcode": "D10942003",
        "std_pid": "H445566778",
        "std_cname": "張偉傑",
        "std_ename": "CHANG,WEI-CHIEH",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "1",
        "std_termcount": "11",
        "std_depno": "PHYS01",
        "dep_depname": "物理學系",
        "std_academyno": "S",
        "aca_cname": "理學院",
        "std_enrolltype": "9",
        "std_directmemo": "碩士逕博",
        "std_highestschname": "清華大學物理學系",
        "com_cellphone": "0966789012",
        "com_email": "chang.phys@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區學府路101號",
        "std_sex": "1",
        "std_enrollyear": "109",
        "std_enrollterm": "1",
        "std_enrolldate": "2020-09"
    },
    "D11242004": {
        "std_stdno": "D112420040",
        "std_stdcode": "D11242004",
        "std_pid": "J556677889",
        "std_cname": "陳思穎",
        "std_ename": "CHEN,SZU-YING",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "1",
        "std_termcount": "5",
        "std_depno": "CHEM01",
        "dep_depname": "化學系",
        "std_academyno": "S",
        "aca_cname": "理學院",
        "std_enrolltype": "1",
        "std_directmemo": "",
        "std_highestschname": "台灣大學化學系",
        "com_cellphone": "0933456789",
        "com_email": "chen.chem@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區南大路101號",
        "std_sex": "2",
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_enrolldate": "2023-09"
    },
    "D10842005": {
        "std_stdno": "D108420050",
        "std_stdcode": "D10842005",
        "std_pid": "K667788990",
        "std_cname": "劉建國",
        "std_ename": "LIU,CHIEN-KUO",
        "std_degree": "1",
        "std_studingstatus": "11",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "1",
        "std_termcount": "13",
        "std_depno": "ME01",
        "dep_depname": "機械工程學系",
        "std_academyno": "I",
        "aca_cname": "工學院",
        "std_enrolltype": "1",
        "std_directmemo": "",
        "std_highestschname": "成功大學機械工程學系",
        "com_cellphone": "0922334455",
        "com_email": "liu.me@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區建功路101號",
        "std_sex": "1",
        "std_enrollyear": "108",
        "std_enrollterm": "1",
        "std_enrolldate": "2019-09"
    },
    "D11342006": {
        "std_stdno": "D113420060",
        "std_stdcode": "D11342006",
        "std_pid": "L778899001",
        "std_cname": "黃詩涵",
        "std_ename": "HUANG,SHIH-HAN",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "2",
        "std_identity": "1",
        "std_termcount": "3",
        "std_depno": "BIO01",
        "dep_depname": "生命科學系",
        "std_academyno": "S",
        "aca_cname": "理學院",
        "std_enrolltype": "2",
        "std_directmemo": "",
        "std_highestschname": "陽明交通大學生物科技學系",
        "com_cellphone": "0911223344",
        "com_email": "huang.bio@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區寶山路101號",
        "std_sex": "2",
        "std_enrollyear": "113",
        "std_enrollterm": "1",
        "std_enrolldate": "2024-09"
    },
    "D11142007": {
        "std_stdno": "D111420070",
        "std_stdcode": "D11142007",
        "std_pid": "M889900112",
        "std_cname": "吳承翰",
        "std_ename": "WU,CHENG-HAN",
        "std_degree": "1",
        "std_studingstatus": "4",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "1",
        "std_termcount": "6",
        "std_depno": "MATH01",
        "dep_depname": "數學系",
        "std_academyno": "S",
        "aca_cname": "理學院",
        "std_enrolltype": "1",
        "std_directmemo": "",
        "std_highestschname": "中央大學數學系",
        "com_cellphone": "0944556677",
        "com_email": "wu.math@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區中華路101號",
        "std_sex": "1",
        "std_enrollyear": "111",
        "std_enrollterm": "1",
        "std_enrolldate": "2022-09"
    },
    
    # Additional PhD Students - Diverse Scenarios
    "D11242008": {
        "std_stdno": "D112420080",
        "std_stdcode": "D11242008",
        "std_pid": "N900112233",
        "std_cname": "趙文華",
        "std_ename": "CHAO,WEN-HUA",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "3",
        "std_termcount": "5",
        "std_depno": "ECON01",
        "dep_depname": "經濟學系",
        "std_academyno": "H",
        "aca_cname": "人文社會學院",
        "std_enrolltype": "3",
        "std_directmemo": "",
        "std_highestschname": "政治大學經濟學系",
        "com_cellphone": "0955667788",
        "com_email": "chao.econ@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區經國路101號",
        "std_sex": "1",
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_enrolldate": "2023-09"
    },
    "D10942009": {
        "std_stdno": "D109420090",
        "std_stdcode": "D10942009",
        "std_pid": "O112233445",
        "std_cname": "許美玲",
        "std_ename": "HSU,MEI-LING",
        "std_degree": "1",
        "std_studingstatus": "2",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "1",
        "std_termcount": "12",
        "std_depno": "MSE01",
        "dep_depname": "材料科學工程學系",
        "std_academyno": "I",
        "aca_cname": "工學院",
        "std_enrolltype": "4",
        "std_directmemo": "",
        "std_highestschname": "台科大材料工程系",
        "com_cellphone": "0933778899",
        "com_email": "hsu.mse@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區材料路101號",
        "std_sex": "2",
        "std_enrollyear": "109",
        "std_enrollterm": "1",
        "std_enrolldate": "2020-09"
    },
    "D11042010": {
        "std_stdno": "D110420100",
        "std_stdcode": "D11042010",
        "std_pid": "P223344556",
        "std_cname": "楊國強",
        "std_ename": "YANG,KUO-CHIANG",
        "std_degree": "1",
        "std_studingstatus": "3",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "1",
        "std_termcount": "10",
        "std_depno": "CHE01",
        "dep_depname": "化學工程學系",
        "std_academyno": "I",
        "aca_cname": "工學院",
        "std_enrolltype": "5",
        "std_directmemo": "",
        "std_highestschname": "交通大學化工系",
        "com_cellphone": "0966889900",
        "com_email": "yang.che@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區化工路101號",
        "std_sex": "1",
        "std_enrollyear": "110",
        "std_enrollterm": "1",
        "std_enrolldate": "2021-09"
    },
    "D11342011": {
        "std_stdno": "D113420110",
        "std_stdcode": "D11342011",
        "std_pid": "Q334455667",
        "std_cname": "蔡佩君",
        "std_ename": "TSAI,PEI-CHUN",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "2",
        "std_schoolid": "1",
        "std_identity": "30",
        "std_termcount": "3",
        "std_depno": "ANTH01",
        "dep_depname": "人類學研究所",
        "std_academyno": "H",
        "aca_cname": "人文社會學院",
        "std_enrolltype": "6",
        "std_directmemo": "",
        "std_highestschname": "香港中文大學人類學系",
        "com_cellphone": "0922445566",
        "com_email": "tsai.anth@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區人文路101號",
        "std_sex": "2",
        "std_enrollyear": "113",
        "std_enrollterm": "1",
        "std_enrolldate": "2024-09"
    },
    "D10842012": {
        "std_stdno": "D108420120",
        "std_stdcode": "D10842012",
        "std_pid": "R445566778",
        "std_cname": "李俊傑",
        "std_ename": "LEE,CHUN-CHIEH",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "2",
        "std_identity": "1",
        "std_termcount": "14",
        "std_depno": "NE01",
        "dep_depname": "核子工程與科學研究所",
        "std_academyno": "I",
        "aca_cname": "工學院",
        "std_enrolltype": "7",
        "std_directmemo": "",
        "std_highestschname": "中原大學核工系",
        "com_cellphone": "0911556677",
        "com_email": "lee.ne@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區核工路101號",
        "std_sex": "1",
        "std_enrollyear": "108",
        "std_enrollterm": "1",
        "std_enrolldate": "2019-09"
    },
    "D11142013": {
        "std_stdno": "D111420130",
        "std_stdcode": "D11142013",
        "std_pid": "S556677889",
        "std_cname": "陳雅純",
        "std_ename": "CHEN,YA-CHUN",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "2",
        "std_termcount": "7",
        "std_depno": "STAT01",
        "dep_depname": "統計學研究所",
        "std_academyno": "S",
        "aca_cname": "理學院",
        "std_enrolltype": "10",
        "std_directmemo": "",
        "std_highestschname": "政治大學統計系",
        "com_cellphone": "0944667788",
        "com_email": "chen.stat@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區統計路101號",
        "std_sex": "2",
        "std_enrollyear": "111",
        "std_enrollterm": "1",
        "std_enrolldate": "2022-09"
    },
    "D11242014": {
        "std_stdno": "D112420140",
        "std_stdcode": "D11242014",
        "std_pid": "T667788990",
        "std_cname": "王建民",
        "std_ename": "WANG,CHIEN-MIN",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "1",
        "std_termcount": "5",
        "std_depno": "PME01",
        "dep_depname": "動力機械工程學系",
        "std_academyno": "I",
        "aca_cname": "工學院",
        "std_enrolltype": "11",
        "std_directmemo": "",
        "std_highestschname": "台大機械系",
        "com_cellphone": "0955778899",
        "com_email": "wang.pme@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區動機路101號",
        "std_sex": "1",
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_enrolldate": "2023-09"
    },
    "D10942015": {
        "std_stdno": "D109420150",
        "std_stdcode": "D10942015",
        "std_pid": "U778899001",
        "std_cname": "張雅芳",
        "std_ename": "CHANG,YA-FANG",
        "std_degree": "1",
        "std_studingstatus": "1",
        "std_nation": "1",
        "std_schoolid": "1",
        "std_identity": "17",
        "std_termcount": "11",
        "std_depno": "LANG01",
        "dep_depname": "外國語文學系",
        "std_academyno": "H",
        "aca_cname": "人文社會學院",
        "std_enrolltype": "12",
        "std_directmemo": "",
        "std_highestschname": "北京大學外國語學院",
        "com_cellphone": "0933889900",
        "com_email": "chang.lang@nthu.edu.tw",
        "com_commzip": "300",
        "com_commadd": "新竹市東區語言路101號",
        "std_sex": "2",
        "std_enrollyear": "109",
        "std_enrollterm": "1",
        "std_enrolldate": "2020-09"
    }
}

SAMPLE_TERMS = {
    "313612215": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "313612215",
            "trm_studystatus": "1",
            "trm_ascore": "86.3",
            "trm_termcount": "3",
            "trm_grade": "1",
            "trm_degree": "3",
            "trm_academyname": "工學院",
            "trm_depname": "電機工程學系",
            "trm_ascore_gpa": "3.8",
            "trm_stdascore": "85.1",
            "trm_placingsrate": "20.3",
            "trm_depplacingrate": "25.6"
        },
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "313612215",
            "trm_studystatus": "1",
            "trm_ascore": "84.2",
            "trm_termcount": "2",
            "trm_grade": "1",
            "trm_degree": "3",
            "trm_academyname": "工學院",
            "trm_depname": "電機工程學系",
            "trm_ascore_gpa": "3.6",
            "trm_stdascore": "83.8",
            "trm_placingsrate": "22.1",
            "trm_depplacingrate": "27.3"
        }
    ],
    "123456789": [
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "123456789",
            "trm_studystatus": "1",
            "trm_ascore": "91.5",
            "trm_termcount": "4",
            "trm_grade": "2",
            "trm_degree": "2",
            "trm_academyname": "資訊學院",
            "trm_depname": "資訊工程學系",
            "trm_ascore_gpa": "4.1",
            "trm_stdascore": "89.7",
            "trm_placingsrate": "15.2",
            "trm_depplacingrate": "18.8"
        }
    ],
    
    # PhD Students Term Data
    "D11142001": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "D11142001",
            "trm_studystatus": "1",
            "trm_ascore": "87.2",
            "trm_termcount": "7",
            "trm_grade": "4",
            "trm_degree": "1",
            "trm_academyname": "工學院",
            "trm_depname": "電機工程學系",
            "trm_ascore_gpa": "3.7",
            "trm_stdascore": "86.8",
            "trm_placingsrate": "12.5",
            "trm_depplacingrate": "15.3"
        },
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "D11142001",
            "trm_studystatus": "1",
            "trm_ascore": "85.6",
            "trm_termcount": "6",
            "trm_grade": "4",
            "trm_degree": "1",
            "trm_academyname": "工學院",
            "trm_depname": "電機工程學系",
            "trm_ascore_gpa": "3.6",
            "trm_stdascore": "84.9",
            "trm_placingsrate": "14.2",
            "trm_depplacingrate": "16.8"
        }
    ],
    "D11042002": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "D11042002",
            "trm_studystatus": "1",
            "trm_ascore": "92.1",
            "trm_termcount": "9",
            "trm_grade": "5",
            "trm_degree": "1",
            "trm_academyname": "資訊學院",
            "trm_depname": "資訊工程學系",
            "trm_ascore_gpa": "4.2",
            "trm_stdascore": "91.3",
            "trm_placingsrate": "8.7",
            "trm_depplacingrate": "11.2"
        }
    ],
    "D10942003": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "D10942003",
            "trm_studystatus": "1",
            "trm_ascore": "89.4",
            "trm_termcount": "11",
            "trm_grade": "6",
            "trm_degree": "1",
            "trm_academyname": "理學院",
            "trm_depname": "物理學系",
            "trm_ascore_gpa": "3.9",
            "trm_stdascore": "88.7",
            "trm_placingsrate": "10.3",
            "trm_depplacingrate": "13.5"
        }
    ],
    "D11242004": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "D11242004",
            "trm_studystatus": "1",
            "trm_ascore": "84.8",
            "trm_termcount": "5",
            "trm_grade": "3",
            "trm_degree": "1",
            "trm_academyname": "理學院",
            "trm_depname": "化學系",
            "trm_ascore_gpa": "3.5",
            "trm_stdascore": "83.9",
            "trm_placingsrate": "18.6",
            "trm_depplacingrate": "22.1"
        }
    ],
    "D10842005": [
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "D10842005",
            "trm_studystatus": "11",
            "trm_ascore": "88.9",
            "trm_termcount": "13",
            "trm_grade": "7",
            "trm_degree": "1",
            "trm_academyname": "工學院",
            "trm_depname": "機械工程學系",
            "trm_ascore_gpa": "3.8",
            "trm_stdascore": "87.5",
            "trm_placingsrate": "11.2",
            "trm_depplacingrate": "14.7"
        }
    ],
    "D11342006": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "D11342006",
            "trm_studystatus": "1",
            "trm_ascore": "86.3",
            "trm_termcount": "3",
            "trm_grade": "2",
            "trm_degree": "1",
            "trm_academyname": "理學院",
            "trm_depname": "生命科學系",
            "trm_ascore_gpa": "3.7",
            "trm_stdascore": "85.8",
            "trm_placingsrate": "16.4",
            "trm_depplacingrate": "19.2"
        }
    ],
    "D11142007": [
        {
            "trm_year": "112",
            "trm_term": "2",
            "trm_stdno": "D11142007",
            "trm_studystatus": "4",
            "trm_ascore": "82.1",
            "trm_termcount": "6",
            "trm_grade": "3",
            "trm_degree": "1",
            "trm_academyname": "理學院",
            "trm_depname": "數學系",
            "trm_ascore_gpa": "3.3",
            "trm_stdascore": "81.5",
            "trm_placingsrate": "24.7",
            "trm_depplacingrate": "28.3"
        }
    ],
    "D11242008": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "D11242008",
            "trm_studystatus": "1",
            "trm_ascore": "88.7",
            "trm_termcount": "5",
            "trm_grade": "3",
            "trm_degree": "1",
            "trm_academyname": "人文社會學院",
            "trm_depname": "經濟學系",
            "trm_ascore_gpa": "3.8",
            "trm_stdascore": "87.9",
            "trm_placingsrate": "13.2",
            "trm_depplacingrate": "16.8"
        }
    ],
    "D10942009": [
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "D10942009",
            "trm_studystatus": "2",
            "trm_ascore": "91.3",
            "trm_termcount": "12",
            "trm_grade": "6",
            "trm_degree": "1",
            "trm_academyname": "工學院",
            "trm_depname": "材料科學工程學系",
            "trm_ascore_gpa": "4.1",
            "trm_stdascore": "90.5",
            "trm_placingsrate": "7.8",
            "trm_depplacingrate": "10.4"
        }
    ],
    "D11042010": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "D11042010",
            "trm_studystatus": "3",
            "trm_ascore": "83.4",
            "trm_termcount": "10",
            "trm_grade": "5",
            "trm_degree": "1",
            "trm_academyname": "工學院",
            "trm_depname": "化學工程學系",
            "trm_ascore_gpa": "3.4",
            "trm_stdascore": "82.7",
            "trm_placingsrate": "21.5",
            "trm_depplacingrate": "25.9"
        }
    ],
    "D11342011": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "D11342011",
            "trm_studystatus": "1",
            "trm_ascore": "85.9",
            "trm_termcount": "3",
            "trm_grade": "2",
            "trm_degree": "1",
            "trm_academyname": "人文社會學院",
            "trm_depname": "人類學研究所",
            "trm_ascore_gpa": "3.6",
            "trm_stdascore": "85.2",
            "trm_placingsrate": "17.3",
            "trm_depplacingrate": "20.8"
        }
    ],
    "D10842012": [
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "D10842012",
            "trm_studingstatus": "1",
            "trm_ascore": "90.1",
            "trm_termcount": "14",
            "trm_grade": "7",
            "trm_degree": "1",
            "trm_academyname": "工學院",
            "trm_depname": "核子工程與科學研究所",
            "trm_ascore_gpa": "4.0",
            "trm_stdascore": "89.3",
            "trm_placingsrate": "9.5",
            "trm_depplacingrate": "12.7"
        }
    ],
    "D11142013": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "D11142013",
            "trm_studystatus": "1",
            "trm_ascore": "87.6",
            "trm_termcount": "7",
            "trm_grade": "4",
            "trm_degree": "1",
            "trm_academyname": "理學院",
            "trm_depname": "統計學研究所",
            "trm_ascore_gpa": "3.7",
            "trm_stdascore": "86.9",
            "trm_placingsrate": "14.8",
            "trm_depplacingrate": "18.1"
        }
    ],
    "D11242014": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "D11242014",
            "trm_studystatus": "1",
            "trm_ascore": "89.2",
            "trm_termcount": "5",
            "trm_grade": "3",
            "trm_degree": "1",
            "trm_academyname": "工學院",
            "trm_depname": "動力機械工程學系",
            "trm_ascore_gpa": "3.9",
            "trm_stdascore": "88.4",
            "trm_placingsrate": "11.7",
            "trm_depplacingrate": "15.2"
        }
    ],
    "D10942015": [
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "D10942015",
            "trm_studystatus": "1",
            "trm_ascore": "84.5",
            "trm_termcount": "11",
            "trm_grade": "6",
            "trm_degree": "1",
            "trm_academyname": "人文社會學院",
            "trm_depname": "外國語文學系",
            "trm_ascore_gpa": "3.5",
            "trm_stdascore": "83.8",
            "trm_placingsrate": "19.2",
            "trm_depplacingrate": "23.6"
        }
    ]
}


def verify_hmac_signature(
    authorization: str,
    request_body: str,
    content_type: str,
    encode_type: Optional[str] = None
) -> bool:
    """
    Verify HMAC-SHA256 signature according to university API specification
    
    Authorization format: HMAC-SHA256:<TIME>:<ACCOUNT>:<SIGNATURE_HEX>
    Message format: <TIME> + <REQUEST_JSON> (no whitespace)
    """
    try:
        # Parse authorization header
        if not authorization.startswith("HMAC-SHA256:"):
            logger.warning(f"Invalid authorization format: {authorization}")
            return False
            
        parts = authorization[12:].split(":")  # Remove "HMAC-SHA256:" prefix
        if len(parts) != 3:
            logger.warning(f"Invalid authorization parts count: {len(parts)}")
            return False
            
        time_str, account, signature_hex = parts
        
        # Validate time format (YYYYMMDDHHMMSS - 14 digits)
        if len(time_str) != 14 or not time_str.isdigit():
            logger.warning(f"Invalid time format: {time_str}")
            return False
            
        # Validate time (±5 minutes tolerance in strict mode)
        if STRICT_TIME_CHECK:
            try:
                request_time = datetime.strptime(time_str, "%Y%m%d%H%M%S")
                current_time = datetime.now()
                time_diff = abs((current_time - request_time).total_seconds() / 60)
                
                if time_diff > TIME_TOLERANCE_MINUTES:
                    logger.warning(f"Time difference too large: {time_diff} minutes")
                    return False
            except ValueError:
                logger.warning(f"Invalid time format for parsing: {time_str}")
                return False
        
        # Check ENCODE_TYPE if strict checking enabled
        if STRICT_ENCODE_CHECK and encode_type != "UTF-8":
            logger.warning(f"Invalid encode type: {encode_type}")
            return False
            
        # Validate Content-Type
        if content_type != "application/json;charset=UTF-8":
            logger.warning(f"Invalid content type: {content_type}")
            return False
            
        # Create message for signature verification
        # Message = TIME + REQUEST_JSON (no spaces, compact JSON)
        message = time_str + request_body
        
        # Get HMAC key from hex
        hmac_key = bytes.fromhex(MOCK_HMAC_KEY_HEX)
        
        # Calculate HMAC-SHA256
        expected_signature = hmac.new(
            hmac_key,
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest().lower()
        
        # Compare signatures
        if signature_hex.lower() != expected_signature:
            logger.warning(f"Signature mismatch. Expected: {expected_signature}, Got: {signature_hex}")
            return False
            
        logger.info(f"HMAC verification successful for account: {account}")
        return True
        
    except Exception as e:
        logger.error(f"HMAC verification error: {str(e)}")
        return False


@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "service": "校計中獎學金學生資料 Mock API",
        "warning": "⚠️ 開發/測試專用 - 請勿用於正式環境 ⚠️",
        "version": "1.0.0",
        "environment": "development",
        "endpoints": {
            "student_basic": "POST /getsoaascholarshipstudent",
            "student_term": "POST /getsoaascholarshipstudentterm",
            "health": "GET /health"
        },
        "authentication": "HMAC-SHA256",
        "strict_mode": STRICT_TIME_CHECK
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "mock-student-api",
        "hmac_key_configured": bool(MOCK_HMAC_KEY_HEX),
        "strict_time_check": STRICT_TIME_CHECK,
        "strict_encode_check": STRICT_ENCODE_CHECK,
        "sample_students": len(SAMPLE_STUDENTS)
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
    獲取獎學金學生基本資料
    
    對應正式 API: POST /getsoaascholarshipstudent
    """
    try:
        # Get raw request body for signature verification
        request_body = await request.body()
        request_json = request_body.decode('utf-8')
        
        # Verify HMAC signature
        if not verify_hmac_signature(authorization, request_json, content_type, encode_type):
            return JSONResponse(
                status_code=401,
                content={
                    "code": 401,
                    "msg": "HMAC signature verification failed",
                    "data": []
                }
            )
        
        # Validate request
        if request.account != "scholarship":
            return JSONResponse(
                status_code=400,
                content={
                    "code": 400,
                    "msg": "Invalid account",
                    "data": []
                }
            )
            
        if request.action != "qrySoaaScholarshipStudent":
            return JSONResponse(
                status_code=400,
                content={
                    "code": 400,
                    "msg": "Invalid action",
                    "data": []
                }
            )
        
        # Get student data
        student_data = SAMPLE_STUDENTS.get(request.stdcode)
        if not student_data:
            return JSONResponse(
                status_code=404,
                content={
                    "code": 404,
                    "msg": "Student not found",
                    "data": []
                }
            )
        
        return {
            "code": 200,
            "msg": "success",
            "data": [student_data]
        }
        
    except Exception as e:
        logger.error(f"Error in get_student_basic_info: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "msg": f"Internal server error: {str(e)}",
                "data": []
            }
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
    獲取獎學金學生學期資料
    
    對應正式 API: POST /getsoaascholarshipstudentterm
    """
    try:
        # Get raw request body for signature verification
        request_body = await request.body()
        request_json = request_body.decode('utf-8')
        
        # Verify HMAC signature
        if not verify_hmac_signature(authorization, request_json, content_type, encode_type):
            return JSONResponse(
                status_code=401,
                content={
                    "code": 401,
                    "msg": "HMAC signature verification failed",
                    "data": []
                }
            )
        
        # Validate request
        if request.account != "scholarship":
            return JSONResponse(
                status_code=400,
                content={
                    "code": 400,
                    "msg": "Invalid account",
                    "data": []
                }
            )
            
        if request.action != "qrySoaaScholarshipStudentTerm":
            return JSONResponse(
                status_code=400,
                content={
                    "code": 400,
                    "msg": "Invalid action",
                    "data": []
                }
            )
        
        # Get student term data
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
                content={
                    "code": 404,
                    "msg": "Term data not found",
                    "data": []
                }
            )
        
        return {
            "code": 200,
            "msg": "success",
            "data": filtered_terms
        }
        
    except Exception as e:
        logger.error(f"Error in get_student_term_info: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "msg": f"Internal server error: {str(e)}",
                "data": []
            }
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)