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
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import logging

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

class APIResponse(BaseModel):
    code: int
    msg: str
    data: List[Any]

# Mock Data synchronized with init_db.py
SAMPLE_STUDENTS = {
    # 對應 init_db.py 中的 stu_under (學士生)
    "stu_under": {
        "std_stdno": "A123456789",
        "std_stdcode": "stu_under",
        "std_pid": "A123456789",
        "std_cname": "學士生",
        "std_ename": "UNDERGRADUATE,STUDENT",
        "std_degree": "3",  # 學士
        "std_studingstatus": "1",  # 在學
        "std_nation": "1",  # 中華民國
        "std_schoolid": "1",  # 一般生
        "std_identity": "1",  # 一般生
        "std_termcount": "2",
        "std_depno": "CS",
        "dep_depname": "資訊工程學系",
        "std_academyno": "EE",
        "aca_cname": "電機資訊學院",
        "std_enrolltype": "1",
        "std_directmemo": "",
        "std_highestschname": "台北市立建國高級中學",
        "com_cellphone": "0912345678",
        "com_email": "stu_under@nycu.edu.tw",
        "com_commzip": "30010",
        "com_commadd": "新竹市東區大學路1001號",
        "std_sex": "1",  # 男
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_enrolldate": "2023-09"
    },
    
    # 對應 init_db.py 中的 stu_phd (博士生)
    "stu_phd": {
        "std_stdno": "B123456789",
        "std_stdcode": "stu_phd", 
        "std_pid": "B123456789",
        "std_cname": "博士生",
        "std_ename": "PHD,STUDENT",
        "std_degree": "1",  # 博士
        "std_studingstatus": "1",  # 在學
        "std_nation": "1",  # 中華民國
        "std_schoolid": "1",  # 一般生
        "std_identity": "1",  # 一般生
        "std_termcount": "1",
        "std_depno": "CS",
        "dep_depname": "資訊工程學系",
        "std_academyno": "EE",
        "aca_cname": "電機資訊學院",
        "std_enrolltype": "1",
        "std_directmemo": "",
        "std_highestschname": "國立交通大學",
        "com_cellphone": "0912345678",
        "com_email": "stu_phd@nycu.edu.tw",
        "com_commzip": "30010",
        "com_commadd": "新竹市東區大學路1001號",
        "std_sex": "1",  # 男
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_enrolldate": "2023-09"
    },
    
    # 對應 init_db.py 中的 stu_direct (逕讀博士生)
    "stu_direct": {
        "std_stdno": "C123456789",
        "std_stdcode": "stu_direct",
        "std_pid": "C123456789", 
        "std_cname": "逕讀博士生",
        "std_ename": "DIRECT,PHD,STUDENT",
        "std_degree": "1",  # 博士
        "std_studingstatus": "1",  # 在學
        "std_nation": "1",  # 中華民國
        "std_schoolid": "1",  # 一般生
        "std_identity": "1",  # 一般生
        "std_termcount": "1",
        "std_depno": "CS",
        "dep_depname": "資訊工程學系",
        "std_academyno": "EE",
        "aca_cname": "電機資訊學院",
        "std_enrolltype": "8",  # 逕讀
        "std_directmemo": "逕讀博士",
        "std_highestschname": "國立陽明交通大學",
        "com_cellphone": "0912345678",
        "com_email": "stu_direct@nycu.edu.tw",
        "com_commzip": "30010",
        "com_commadd": "新竹市東區大學路1001號",
        "std_sex": "2",  # 女
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_enrolldate": "2023-09"
    },
    
    # 對應 init_db.py 中的 stu_master (碩士生)
    "stu_master": {
        "std_stdno": "D123456789",
        "std_stdcode": "stu_master",
        "std_pid": "D123456789",
        "std_cname": "碩士生",
        "std_ename": "MASTER,STUDENT",
        "std_degree": "2",  # 碩士
        "std_studingstatus": "1",  # 在學
        "std_nation": "1",  # 中華民國
        "std_schoolid": "1",  # 一般生
        "std_identity": "1",  # 一般生
        "std_termcount": "1",
        "std_depno": "CS",
        "dep_depname": "資訊工程學系",
        "std_academyno": "EE",
        "aca_cname": "電機資訊學院",
        "std_enrolltype": "1",
        "std_directmemo": "",
        "std_highestschname": "國立台灣大學",
        "com_cellphone": "0912345678",
        "com_email": "stu_master@nycu.edu.tw",
        "com_commzip": "30010",
        "com_commadd": "新竹市東區大學路1001號",
        "std_sex": "2",  # 女
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_enrolldate": "2023-09"
    },
    
    # 對應 init_db.py 中的 phd_china (陸生博士)
    "phd_china": {
        "std_stdno": "E123456789",
        "std_stdcode": "phd_china",
        "std_pid": "E123456789",
        "std_cname": "陸生",
        "std_ename": "CHINA,PHD,STUDENT",
        "std_degree": "1",  # 博士
        "std_studingstatus": "1",  # 在學
        "std_nation": "2",  # 非中華民國國籍
        "std_schoolid": "1",  # 一般生
        "std_identity": "17",  # 陸生
        "std_termcount": "1",
        "std_depno": "CS",
        "dep_depname": "資訊工程學系", 
        "std_academyno": "EE",
        "aca_cname": "電機資訊學院",
        "std_enrolltype": "1",
        "std_directmemo": "",
        "std_highestschname": "國立清華大學",
        "com_cellphone": "0912345678",
        "com_email": "phd_china@nycu.edu.tw",
        "com_commzip": "30010",
        "com_commadd": "新竹市東區大學路1001號",
        "std_sex": "1",  # 男
        "std_enrollyear": "112",
        "std_enrollterm": "1",
        "std_enrolldate": "2023-09"
    },
    
    # 原有的測試學生資料保留用於測試
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
    }
}

SAMPLE_TERMS = {
    "stu_under": [
        {
            "trm_year": "113",
            "trm_term": "2",
            "trm_stdno": "stu_under",
            "trm_studystatus": "1",
            "trm_ascore": "82.5",
            "trm_termcount": "2",
            "trm_grade": "2",  # 二年級
            "trm_degree": "3",  # 學士
            "trm_academyname": "電機資訊學院",
            "trm_depname": "資訊工程學系",
            "trm_ascore_gpa": "3.5",
            "trm_stdascore": "81.8",
            "trm_placingsrate": "25.3",
            "trm_depplacingrate": "30.1"
        }
    ],
    "stu_phd": [
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "stu_phd",
            "trm_studystatus": "1",
            "trm_ascore": "90.2",
            "trm_termcount": "1",
            "trm_grade": "1",  # 一年級
            "trm_degree": "1",  # 博士
            "trm_academyname": "電機資訊學院",
            "trm_depname": "資訊工程學系",
            "trm_ascore_gpa": "4.1",
            "trm_stdascore": "89.5",
            "trm_placingsrate": "8.7",
            "trm_depplacingrate": "12.3"
        }
    ],
    "stu_direct": [
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "stu_direct",
            "trm_studystatus": "1",
            "trm_ascore": "88.9",
            "trm_termcount": "1",
            "trm_grade": "1",  # 一年級
            "trm_degree": "1",  # 博士
            "trm_academyname": "電機資訊學院",
            "trm_depname": "資訊工程學系",
            "trm_ascore_gpa": "3.9",
            "trm_stdascore": "87.2",
            "trm_placingsrate": "10.5",
            "trm_depplacingrate": "15.2"
        }
    ],
    "stu_master": [
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "stu_master",
            "trm_studystatus": "1",
            "trm_ascore": "85.7",
            "trm_termcount": "1",
            "trm_grade": "1",  # 一年級
            "trm_degree": "2",  # 碩士
            "trm_academyname": "電機資訊學院",
            "trm_depname": "資訊工程學系",
            "trm_ascore_gpa": "3.7",
            "trm_stdascore": "84.3",
            "trm_placingsrate": "18.2",
            "trm_depplacingrate": "22.8"
        }
    ],
    "phd_china": [
        {
            "trm_year": "113",
            "trm_term": "1",
            "trm_stdno": "phd_china",
            "trm_studystatus": "1",
            "trm_ascore": "92.1",
            "trm_termcount": "1",
            "trm_grade": "1",  # 一年級
            "trm_degree": "1",  # 博士
            "trm_academyname": "電機資訊學院",
            "trm_depname": "資訊工程學系",
            "trm_ascore_gpa": "4.2",
            "trm_stdascore": "91.3",
            "trm_placingsrate": "5.2",
            "trm_depplacingrate": "8.9"
        }
    ],
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
    
    Note: TIME should be in UTC format (YYYYMMDDHHMMSS)
    """
    try:
        if not authorization.startswith("HMAC-SHA256:"):
            logger.warning(f"Invalid authorization format: {authorization}")
            return False
            
        parts = authorization[12:].split(":")
        if len(parts) != 3:
            logger.warning(f"Invalid authorization parts count: {len(parts)}")
            return False
            
        time_str, account, signature_hex = parts
        
        if len(time_str) != 14 or not time_str.isdigit():
            logger.warning(f"Invalid time format: {time_str}")
            return False
            
        if STRICT_TIME_CHECK:
            try:
                request_time = datetime.strptime(time_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                current_time = datetime.now(timezone.utc)
                time_diff = abs((current_time - request_time).total_seconds() / 60)
                
                if time_diff > TIME_TOLERANCE_MINUTES:
                    logger.warning(f"Time difference too large: {time_diff} minutes")
                    return False
            except ValueError:
                logger.warning(f"Invalid time format for parsing: {time_str}")
                return False
        
        if STRICT_ENCODE_CHECK and encode_type != "UTF-8":
            logger.warning(f"Invalid encode type: {encode_type}")
            return False
            
        if content_type != "application/json;charset=UTF-8":
            logger.warning(f"Invalid content type: {content_type}")
            return False
            
        message = time_str + request_body
        hmac_key = bytes.fromhex(MOCK_HMAC_KEY_HEX)
        
        expected_signature = hmac.new(
            hmac_key,
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest().lower()
        
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
        "version": "2.1.0",
        "environment": "development",
        "data_source": "in-memory (synchronized with init_db.py)",
        "endpoints": {
            "student_basic": "POST /getsoaascholarshipstudent",
            "student_term": "POST /getsoaascholarshipstudentterm",
            "health": "GET /health"
        },
        "authentication": "HMAC-SHA256",
        "strict_mode": STRICT_TIME_CHECK,
        "available_students": list(SAMPLE_STUDENTS.keys())
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
        
        if request.account != "scholarship":
            return JSONResponse(
                status_code=400,
                content={"code": 400, "msg": "Invalid account", "data": []}
            )
            
        if request.action != "qrySoaaScholarshipStudent":
            return JSONResponse(
                status_code=400,
                content={"code": 400, "msg": "Invalid action", "data": []}
            )
        
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
            content={"code": 500, "msg": f"Internal server error: {str(e)}", "data": []}
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
        
        if request.account != "scholarship":
            return JSONResponse(
                status_code=400, 
                content={"code": 400, "msg": "Invalid account", "data": []}
            )
            
        if request.action != "qrySoaaScholarshipStudentTerm":
            return JSONResponse(
                status_code=400,
                content={"code": 400, "msg": "Invalid action", "data": []}
            )
        
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
            content={"code": 500, "msg": f"Internal server error: {str(e)}", "data": []}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)