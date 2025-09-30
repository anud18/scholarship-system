"""
Mock Student Database API with HMAC-SHA256 Authentication and Database Integration

⚠️ DEVELOPMENT/TESTING ONLY ⚠️
Mock API for student database access during development.
DO NOT USE IN PRODUCTION.

Implements HMAC-SHA256 signature verification compatible with the university's
student information system API endpoints, now with real database integration.
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="校計中獎學金學生資料 Mock API", description="⚠️ 開發/測試專用 ⚠️ 模擬校計中 API，支援 HMAC-SHA256 驗簽，連接真實資料庫", version="2.0.0"
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
MOCK_HMAC_KEY_HEX = os.getenv(
    "MOCK_HMAC_KEY_HEX", "4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a"
)
STRICT_TIME_CHECK = os.getenv("STRICT_TIME_CHECK", "true").lower() == "true"
STRICT_ENCODE_CHECK = os.getenv("STRICT_ENCODE_CHECK", "false").lower() == "true"
TIME_TOLERANCE_MINUTES = int(os.getenv("TIME_TOLERANCE_MINUTES", "5"))

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scholarship_user:scholarship_pass@postgres:5432/scholarship_db")

# Create database engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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


# Database Helper Functions
def get_student_from_db(stdcode: str) -> Optional[Dict[str, str]]:
    """Get student basic information from database"""
    db = SessionLocal()
    try:
        query = text(
            """
            SELECT
                std_stdno,
                std_stdcode,
                std_pid,
                std_cname,
                std_ename,
                std_degree,
                std_studingstatus,
                std_nation,
                std_schoolid,
                std_identity,
                COALESCE(std_termcount::text, '0') as std_termcount,
                std_depno,
                std_depname as dep_depname,
                std_aca_no,
                std_aca_cname as aca_cname,
                '1' as std_enrolltype,  -- Default value
                '' as std_directmemo,
                std_highestschname,
                com_cellphone,
                com_email,
                com_commzip,
                com_commadd,
                std_sex,
                std_enrollyear,
                std_enrollterm,
                TO_CHAR(std_enrolled_date, 'YYYY-MM') as std_enrolldate
            FROM students
            WHERE std_stdcode = :stdcode
        """
        )

        result = db.execute(query, {"stdcode": stdcode}).fetchone()

        if result:
            return {
                "std_stdno": str(result.std_stdno or ""),
                "std_stdcode": str(result.std_stdcode or ""),
                "std_pid": str(result.std_pid or ""),
                "std_cname": str(result.std_cname or ""),
                "std_ename": str(result.std_ename or ""),
                "std_degree": str(result.std_degree or ""),
                "std_studingstatus": str(result.std_studingstatus or ""),
                "std_nation": str(result.std_nation or ""),
                "std_schoolid": str(result.std_schoolid or ""),
                "std_identity": str(result.std_identity or ""),
                "std_termcount": str(result.std_termcount or "0"),
                "std_depno": str(result.std_depno or ""),
                "dep_depname": str(result.dep_depname or ""),
                "std_academyno": str(result.std_aca_no or ""),
                "aca_cname": str(result.aca_cname or ""),
                "std_enrolltype": str(result.std_enrolltype or "1"),
                "std_directmemo": str(result.std_directmemo or ""),
                "std_highestschname": str(result.std_highestschname or ""),
                "com_cellphone": str(result.com_cellphone or ""),
                "com_email": str(result.com_email or ""),
                "com_commzip": str(result.com_commzip or ""),
                "com_commadd": str(result.com_commadd or ""),
                "std_sex": str(result.std_sex or ""),
                "std_enrollyear": str(result.std_enrollyear or ""),
                "std_enrollterm": str(result.std_enrollterm or ""),
                "std_enrolldate": str(result.std_enrolldate or ""),
            }

        return None

    except Exception as e:
        logger.error(f"Database error in get_student_from_db: {str(e)}")
        return None
    finally:
        db.close()


def get_student_terms_from_db(stdcode: str, trmyear: str, trmterm: str) -> List[Dict[str, str]]:
    """Get student term data - mock implementation based on student existence"""
    student = get_student_from_db(stdcode)
    if not student:
        return []

    # Generate realistic mock term data based on student info
    mock_term = {
        "trm_year": str(trmyear),
        "trm_term": str(trmterm),
        "trm_stdno": str(stdcode),
        "trm_studystatus": str(student.get("std_studingstatus", "1")),
        "trm_ascore": "85.0",
        "trm_termcount": str(student.get("std_termcount", "1")),
        "trm_grade": "1" if student.get("std_degree") == "3" else ("2" if student.get("std_degree") == "2" else "4"),
        "trm_degree": str(student.get("std_degree", "3")),
        "trm_academyname": str(student.get("aca_cname", "")),
        "trm_depname": str(student.get("dep_depname", "")),
        "trm_ascore_gpa": "3.7",
        "trm_stdascore": "84.5",
        "trm_placingsrate": "20.0",
        "trm_depplacingrate": "25.0",
    }

    return [mock_term]


def verify_hmac_signature(
    authorization: str, request_body: str, content_type: str, encode_type: Optional[str] = None
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

        expected_signature = hmac.new(hmac_key, message.encode("utf-8"), hashlib.sha256).hexdigest().lower()

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
        "version": "2.0.0",
        "environment": "development",
        "database_integration": True,
        "endpoints": {
            "student_basic": "POST /getsoaascholarshipstudent",
            "student_term": "POST /getsoaascholarshipstudentterm",
            "health": "GET /health",
        },
        "authentication": "HMAC-SHA256",
        "strict_mode": STRICT_TIME_CHECK,
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    db_status = "connected"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy",
        "service": "mock-student-api",
        "version": "2.0.0",
        "database_status": db_status,
        "hmac_key_configured": bool(MOCK_HMAC_KEY_HEX),
        "strict_time_check": STRICT_TIME_CHECK,
        "strict_encode_check": STRICT_ENCODE_CHECK,
    }


@app.post("/getsoaascholarshipstudent")
async def get_student_basic_info(
    request: StudentBasicRequest,
    request_obj: Request,
    authorization: str = Header(..., description="HMAC-SHA256 authorization header"),
    content_type: str = Header(..., alias="content-type"),
    encode_type: Optional[str] = Header(None, alias="ENCODE_TYPE"),
):
    """
    獲取獎學金學生基本資料 - 從資料庫取得真實資料

    對應正式 API: POST /getsoaascholarshipstudent
    """
    try:
        request_body = await request_obj.body()
        request_json = request_body.decode("utf-8")

        if not verify_hmac_signature(authorization, request_json, content_type, encode_type):
            return JSONResponse(
                status_code=401, content={"code": 401, "msg": "HMAC signature verification failed", "data": []}
            )

        if request.account != "scholarship":
            return JSONResponse(status_code=400, content={"code": 400, "msg": "Invalid account", "data": []})

        if request.action != "qrySoaaScholarshipStudent":
            return JSONResponse(status_code=400, content={"code": 400, "msg": "Invalid action", "data": []})

        # Get student data from database
        student_data = get_student_from_db(request.stdcode)
        if not student_data:
            return JSONResponse(status_code=404, content={"code": 404, "msg": "Student not found", "data": []})

        return {"code": 200, "msg": "success", "data": [student_data]}

    except Exception as e:
        logger.error(f"Error in get_student_basic_info: {str(e)}")
        return JSONResponse(
            status_code=500, content={"code": 500, "msg": f"Internal server error: {str(e)}", "data": []}
        )


@app.post("/getsoaascholarshipstudentterm")
async def get_student_term_info(
    request: StudentTermRequest,
    request_obj: Request,
    authorization: str = Header(..., description="HMAC-SHA256 authorization header"),
    content_type: str = Header(..., alias="content-type"),
    encode_type: Optional[str] = Header(None, alias="ENCODE_TYPE"),
):
    """
    獲取獎學金學生學期資料 - 基於資料庫學生資料產生模擬學期資料

    對應正式 API: POST /getsoaascholarshipstudentterm
    """
    try:
        request_body = await request_obj.body()
        request_json = request_body.decode("utf-8")

        if not verify_hmac_signature(authorization, request_json, content_type, encode_type):
            return JSONResponse(
                status_code=401, content={"code": 401, "msg": "HMAC signature verification failed", "data": []}
            )

        if request.account != "scholarship":
            return JSONResponse(status_code=400, content={"code": 400, "msg": "Invalid account", "data": []})

        if request.action != "qrySoaaScholarshipStudentTerm":
            return JSONResponse(status_code=400, content={"code": 400, "msg": "Invalid action", "data": []})

        # Get student term data
        filtered_terms = get_student_terms_from_db(request.stdcode, request.trmyear, request.trmterm)

        if not filtered_terms:
            return JSONResponse(status_code=404, content={"code": 404, "msg": "Term data not found", "data": []})

        return {"code": 200, "msg": "success", "data": filtered_terms}

    except Exception as e:
        logger.error(f"Error in get_student_term_info: {str(e)}")
        return JSONResponse(
            status_code=500, content={"code": 500, "msg": f"Internal server error: {str(e)}", "data": []}
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
