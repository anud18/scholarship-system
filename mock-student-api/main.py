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