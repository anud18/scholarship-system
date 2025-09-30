"""
Comprehensive test suite for HMAC-SHA256 authenticated Mock Student Database API

⚠️ DEVELOPMENT/TESTING ONLY ⚠️
Test cases for the university's student information system API mock implementation.
"""

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

import requests


class HMACAPIClient:
    """Client for testing HMAC-SHA256 authenticated API endpoints"""

    def __init__(self, base_url: str = "http://localhost:8080", hmac_key_hex: str = None):
        self.base_url = base_url
        self.hmac_key_hex = (
            hmac_key_hex or "4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a"
        )
        self.account = "scholarship"
        print(f"Testing API at: {self.base_url}")
        print(f"Database integration: This will test against real student data from the scholarship database")

    def _generate_hmac_signature(self, request_body: str, timestamp: str) -> str:
        """Generate HMAC-SHA256 signature for API request"""
        # Message = TIME + REQUEST_JSON (no spaces, compact JSON)
        message = timestamp + request_body

        # Get HMAC key from hex
        hmac_key = bytes.fromhex(self.hmac_key_hex)

        # Calculate HMAC-SHA256
        signature = hmac.new(hmac_key, message.encode("utf-8"), hashlib.sha256).hexdigest().lower()

        return signature

    def _make_authenticated_request(self, endpoint: str, request_data: Dict[str, Any]) -> requests.Response:
        """Make authenticated request to API endpoint"""
        # Generate timestamp (YYYYMMDDHHMMSS) - UTC
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        # Create compact JSON (no spaces)
        request_body = json.dumps(request_data, separators=(",", ":"), ensure_ascii=False)

        # Generate signature
        signature = self._generate_hmac_signature(request_body, timestamp)

        # Create authorization header
        authorization = f"HMAC-SHA256:{timestamp}:{self.account}:{signature}"

        # Set headers
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json;charset=UTF-8",
            "ENCODE_TYPE": "UTF-8",
        }

        # Make request
        url = f"{self.base_url}{endpoint}"
        response = requests.post(url, data=request_body, headers=headers)

        return response

    def get_student_basic_info(self, stdcode: str) -> requests.Response:
        """Get student basic information"""
        request_data = {"account": self.account, "action": "qrySoaaScholarshipStudent", "stdcode": stdcode}
        return self._make_authenticated_request("/getsoaascholarshipstudent", request_data)

    def get_student_term_info(self, stdcode: str, trmyear: str, trmterm: str) -> requests.Response:
        """Get student semester information"""
        request_data = {
            "account": self.account,
            "action": "qrySoaaScholarshipStudentTerm",
            "stdcode": stdcode,
            "trmyear": trmyear,
            "trmterm": trmterm,
        }
        return self._make_authenticated_request("/getsoaascholarshipstudentterm", request_data)


def test_health_endpoint():
    """Test health check endpoint"""
    print("🔍 Testing health endpoint...")
    response = requests.get("http://localhost:8080/health")

    assert response.status_code == 200, f"Health check failed: {response.status_code}"

    data = response.json()
    assert data["status"] == "healthy", "Service is not healthy"
    assert data["service"] == "mock-student-api", "Incorrect service name"

    print("✅ Health endpoint working correctly")
    return True


def test_root_endpoint():
    """Test root endpoint"""
    print("🔍 Testing root endpoint...")
    response = requests.get("http://localhost:8080/")

    assert response.status_code == 200, f"Root endpoint failed: {response.status_code}"

    data = response.json()
    assert "service" in data, "Service info missing"
    assert "endpoints" in data, "Endpoint info missing"
    assert data["authentication"] == "HMAC-SHA256", "Authentication type incorrect"

    print("✅ Root endpoint working correctly")
    return True


def test_student_basic_info_valid():
    """Test valid student basic information request"""
    print("🔍 Testing valid student basic info request...")

    client = HMACAPIClient()
    response = client.get_student_basic_info("313612215")

    assert response.status_code == 200, f"Request failed: {response.status_code} - {response.text}"

    data = response.json()
    assert data["code"] == 200, f"API error: {data.get('msg', 'Unknown error')}"
    assert data["msg"] == "success", f"Unexpected message: {data['msg']}"
    assert len(data["data"]) == 1, f"Expected 1 student record, got {len(data['data'])}"

    student = data["data"][0]
    assert student["std_stdcode"] == "313612215", "Student code mismatch"
    assert student["std_cname"] == "陳弘穎", "Student name mismatch"
    assert student["std_ename"] == "CHEN,HUNG-YING", "English name mismatch"

    print("✅ Valid student basic info request working correctly")
    return True


def test_student_basic_info_not_found():
    """Test student not found scenario"""
    print("🔍 Testing student not found scenario...")

    client = HMACAPIClient()
    response = client.get_student_basic_info("999999999")

    assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    data = response.json()
    assert data["code"] == 404, f"Expected error code 404, got {data['code']}"
    assert "not found" in data["msg"].lower(), f"Unexpected error message: {data['msg']}"

    print("✅ Student not found scenario working correctly")
    return True


def test_student_term_info_valid():
    """Test valid student term information request"""
    print("🔍 Testing valid student term info request...")

    client = HMACAPIClient()
    response = client.get_student_term_info("313612215", "113", "2")

    assert response.status_code == 200, f"Request failed: {response.status_code} - {response.text}"

    data = response.json()
    assert data["code"] == 200, f"API error: {data.get('msg', 'Unknown error')}"
    assert data["msg"] == "success", f"Unexpected message: {data['msg']}"
    assert len(data["data"]) == 1, f"Expected 1 term record, got {len(data['data'])}"

    term = data["data"][0]
    assert term["trm_year"] == "113", "Academic year mismatch"
    assert term["trm_term"] == "2", "Academic term mismatch"
    assert term["std_stdcode"] == "313612215", "Student code mismatch"

    print("✅ Valid student term info request working correctly")
    return True


def test_student_term_info_not_found():
    """Test term data not found scenario"""
    print("🔍 Testing term data not found scenario...")

    client = HMACAPIClient()
    response = client.get_student_term_info("313612215", "999", "1")

    assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    data = response.json()
    assert data["code"] == 404, f"Expected error code 404, got {data['code']}"
    assert "not found" in data["msg"].lower(), f"Unexpected error message: {data['msg']}"

    print("✅ Term data not found scenario working correctly")
    return True


def test_invalid_hmac_signature():
    """Test invalid HMAC signature rejection"""
    print("🔍 Testing invalid HMAC signature rejection...")

    # Create request with invalid signature
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    request_data = {"account": "scholarship", "action": "qrySoaaScholarshipStudent", "stdcode": "313612215"}
    request_body = json.dumps(request_data, separators=(",", ":"), ensure_ascii=False)

    # Use invalid signature
    invalid_signature = "invalid_signature_12345"
    authorization = f"HMAC-SHA256:{timestamp}:scholarship:{invalid_signature}"

    headers = {"Authorization": authorization, "Content-Type": "application/json;charset=UTF-8", "ENCODE_TYPE": "UTF-8"}

    response = requests.post("http://localhost:8080/getsoaascholarshipstudent", data=request_body, headers=headers)

    assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    data = response.json()
    assert data["code"] == 401, f"Expected error code 401, got {data['code']}"
    assert "signature" in data["msg"].lower(), f"Unexpected error message: {data['msg']}"

    print("✅ Invalid HMAC signature rejection working correctly")
    return True


def test_invalid_account():
    """Test invalid account rejection"""
    print("🔍 Testing invalid account rejection...")

    # Create client with valid HMAC but invalid account
    client = HMACAPIClient()
    request_data = {"account": "invalid_account", "action": "qrySoaaScholarshipStudent", "stdcode": "313612215"}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    request_body = json.dumps(request_data, separators=(",", ":"), ensure_ascii=False)
    signature = client._generate_hmac_signature(request_body, timestamp)
    authorization = f"HMAC-SHA256:{timestamp}:scholarship:{signature}"

    headers = {"Authorization": authorization, "Content-Type": "application/json;charset=UTF-8", "ENCODE_TYPE": "UTF-8"}

    response = requests.post("http://localhost:8080/getsoaascholarshipstudent", data=request_body, headers=headers)

    assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    data = response.json()
    assert data["code"] == 400, f"Expected error code 400, got {data['code']}"
    assert "account" in data["msg"].lower(), f"Unexpected error message: {data['msg']}"

    print("✅ Invalid account rejection working correctly")
    return True


def test_invalid_action():
    """Test invalid action rejection"""
    print("🔍 Testing invalid action rejection...")

    client = HMACAPIClient()
    request_data = {"account": "scholarship", "action": "invalidAction", "stdcode": "313612215"}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    request_body = json.dumps(request_data, separators=(",", ":"), ensure_ascii=False)
    signature = client._generate_hmac_signature(request_body, timestamp)
    authorization = f"HMAC-SHA256:{timestamp}:scholarship:{signature}"

    headers = {"Authorization": authorization, "Content-Type": "application/json;charset=UTF-8", "ENCODE_TYPE": "UTF-8"}

    response = requests.post("http://localhost:8080/getsoaascholarshipstudent", data=request_body, headers=headers)

    assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    data = response.json()
    assert data["code"] == 400, f"Expected error code 400, got {data['code']}"
    assert "action" in data["msg"].lower(), f"Unexpected error message: {data['msg']}"

    print("✅ Invalid action rejection working correctly")
    return True


def test_missing_authorization_header():
    """Test missing authorization header rejection"""
    print("🔍 Testing missing authorization header rejection...")

    request_data = {"account": "scholarship", "action": "qrySoaaScholarshipStudent", "stdcode": "313612215"}
    request_body = json.dumps(request_data, separators=(",", ":"), ensure_ascii=False)

    headers = {"Content-Type": "application/json;charset=UTF-8"}

    response = requests.post("http://localhost:8080/getsoaascholarshipstudent", data=request_body, headers=headers)

    # FastAPI will return 422 for missing required header
    assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    print("✅ Missing authorization header rejection working correctly")
    return True


def test_sample_data_completeness():
    """Test that sample data contains all required fields"""
    print("🔍 Testing sample data completeness...")

    client = HMACAPIClient()

    # Test student basic info fields - 根據實際API格式
    response = client.get_student_basic_info("313612215")
    assert response.status_code == 200

    student = response.json()["data"][0]
    # 只檢查實際API中存在的欄位
    required_student_fields = [
        "std_stdcode",
        "std_enrollyear",
        "std_enrollterm",
        "std_highestschname",
        "std_cname",
        "std_ename",
        "std_pid",
        "std_academyno",
        "std_depno",
        "std_sex",
        "std_nation",
        "std_degree",
        "std_enrolltype",
        "std_identity",
        "std_schoolid",
        "std_overseaplace",
        "std_termcount",
        "mgd_title",
        "ToDoctor",
        "com_commadd",
        "com_email",
        "com_cellphone",
    ]

    for field in required_student_fields:
        assert field in student, f"Missing required field: {field}"

    # Test term info fields - 根據實際API格式
    response = client.get_student_term_info("313612215", "113", "2")
    assert response.status_code == 200

    term = response.json()["data"][0]
    # 只檢查實際API中存在的欄位
    required_term_fields = [
        "std_stdcode",
        "trm_year",
        "trm_term",
        "trm_termcount",
        "trm_studystatus",
        "trm_degree",
        "trm_academyno",
        "trm_depno",
        "trm_placings",
        "trm_depplacing",
        "trm_ascore_gpa",
    ]

    for field in required_term_fields:
        assert field in term, f"Missing required field: {field}"

    print("✅ Sample data completeness verified")
    return True


def run_all_tests():
    """Run all test cases"""
    print("🧪 Starting comprehensive API tests...\n")

    test_functions = [
        test_health_endpoint,
        test_root_endpoint,
        test_student_basic_info_valid,
        test_student_basic_info_not_found,
        test_student_term_info_valid,
        test_student_term_info_not_found,
        test_invalid_hmac_signature,
        test_invalid_account,
        test_invalid_action,
        test_missing_authorization_header,
        test_sample_data_completeness,
    ]

    passed = 0
    failed = 0

    for test_func in test_functions:
        try:
            test_func()
            passed += 1
            print()
        except Exception as e:
            print(f"❌ Test failed: {test_func.__name__}")
            print(f"   Error: {str(e)}\n")
            failed += 1

    print(f"📊 Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All tests passed! API is working correctly.")
        return True
    else:
        print(f"⚠️  {failed} test(s) failed. Please check the implementation.")
        return False


if __name__ == "__main__":
    # Check if API is running
    try:
        response = requests.get("http://localhost:8080/health", timeout=5)
        if response.status_code != 200:
            print("❌ API is not responding correctly. Please start the server first:")
            print("   python main.py")
            exit(1)
    except requests.exceptions.RequestException:
        print("❌ Cannot connect to API. Please start the server first:")
        print("   python main.py")
        exit(1)

    # Run all tests
    success = run_all_tests()
    exit(0 if success else 1)
