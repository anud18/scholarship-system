"""
學籍驗證服務
Student verification service for checking student enrollment status
"""

import logging
from datetime import datetime
from typing import Any, Dict

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from app.core.config import settings
from app.core.exceptions import StudentVerificationError
from app.models.payment_roster import StudentVerificationStatus

logger = logging.getLogger(__name__)


class StudentVerificationService:
    """學籍驗證服務"""

    def __init__(self):
        self.session = self._create_session()
        self.api_base_url = getattr(settings, "STUDENT_VERIFICATION_API_URL", None)
        self.api_key = getattr(settings, "STUDENT_VERIFICATION_API_KEY", None)
        self.mock_mode = getattr(settings, "STUDENT_VERIFICATION_MOCK_MODE", True)
        self.timeout = 30  # seconds

    def _create_session(self) -> requests.Session:
        """建立HTTP session with retry strategy"""
        session = requests.Session()

        # Retry strategy
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "POST"],
            backoff_factor=1,
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def verify_student(self, student_id_number: str, student_name: str) -> Dict[str, Any]:
        """
        驗證學生身分

        Args:
            student_id_number: 學生身分證字號
            student_name: 學生姓名

        Returns:
            Dict[str, Any]: 驗證結果
            {
                "status": StudentVerificationStatus,
                "message": str,
                "student_info": Dict[str, Any],
                "verified_at": datetime,
                "api_response": Dict[str, Any]
            }

        Raises:
            StudentVerificationError: 驗證過程中發生錯誤
        """
        try:
            if self.mock_mode:
                return self._mock_verification(student_id_number, student_name)
            else:
                return self._api_verification(student_id_number, student_name)

        except Exception as e:
            logger.error(f"Student verification failed for {student_id_number}: {e}")
            return {
                "status": StudentVerificationStatus.API_ERROR,
                "message": f"驗證過程發生錯誤: {str(e)}",
                "student_info": {},
                "verified_at": datetime.now(),
                "api_response": {"error": str(e)},
            }

    def _mock_verification(self, student_id_number: str, student_name: str) -> Dict[str, Any]:
        """
        模擬驗證 (開發測試用)
        根據身分證字號末位數字決定驗證結果
        """
        logger.info(f"Mock verification for {student_id_number} ({student_name})")

        # 根據身分證字號末位數字決定狀態
        last_digit = int(student_id_number[-1]) if student_id_number[-1].isdigit() else 0

        if last_digit <= 6:
            status = StudentVerificationStatus.VERIFIED
            message = "學籍驗證通過"
            # 模擬API回傳的完整學生資料（可能與申請時的資料有差異）
            student_info = {
                "student_id": student_id_number,
                "name": student_name,
                "school_code": "NCTU",
                "school_name": "國立陽明交通大學",
                "department": "資訊工程學系",
                "grade": "博士班二年級",
                "enrollment_status": "在學",
                "enrollment_date": "2022-09-01",
                "gpa": round(3.5 + (last_digit * 0.1), 2),  # 模擬GPA可能有變化
                "email": f"{student_name.replace(' ', '').lower()}@m{last_digit:02d}.nycu.edu.tw",  # 模擬Email可能有更新
                "phone": f"0912-{last_digit:03d}{last_digit:03d}",  # 模擬電話可能有更新
                "address": f"新竹市大學路{last_digit+1000}號",  # 模擬地址可能有更新
                "bank_account": f"12345678{last_digit}",  # 銀行帳號
                "bank_code": "012",
                "bank_name": "台灣銀行",
            }
        elif last_digit == 7:
            status = StudentVerificationStatus.GRADUATED
            message = "學生已畢業"
            student_info = {
                "student_id": student_id_number,
                "name": student_name,
                "graduation_date": "2023-06-30",
                "degree": "博士",
            }
        elif last_digit == 8:
            status = StudentVerificationStatus.SUSPENDED
            message = "學生目前休學中"
            student_info = {
                "student_id": student_id_number,
                "name": student_name,
                "suspension_start": "2024-02-01",
                "suspension_reason": "個人因素",
            }
        elif last_digit == 9:
            status = StudentVerificationStatus.WITHDRAWN
            message = "學生已退學"
            student_info = {
                "student_id": student_id_number,
                "name": student_name,
                "withdrawal_date": "2024-01-15",
                "withdrawal_reason": "志趣不符",
            }
        else:
            status = StudentVerificationStatus.NOT_FOUND
            message = "查無此學生資料"
            student_info = {}

        return {
            "status": status,
            "message": message,
            "student_info": student_info,
            "verified_at": datetime.now(),
            "api_response": {
                "mock": True,
                "last_digit": last_digit,
            },
        }

    def _api_verification(self, student_id_number: str, student_name: str) -> Dict[str, Any]:
        """
        透過API進行真實驗證
        """
        if not self.api_base_url or not self.api_key:
            raise StudentVerificationError(
                "Student verification API is not configured",
                student_id=student_id_number,
            )

        logger.info(f"API verification for {student_id_number} ({student_name})")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "student_id": student_id_number,
            "student_name": student_name,
        }

        try:
            response = self.session.post(
                f"{self.api_base_url}/verify",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                data = response.json()
                return self._parse_api_response(data, student_id_number)
            elif response.status_code == 404:
                return {
                    "status": StudentVerificationStatus.NOT_FOUND,
                    "message": "查無此學生資料",
                    "student_info": {},
                    "verified_at": datetime.now(),
                    "api_response": response.json() if response.text else {},
                }
            else:
                raise StudentVerificationError(
                    f"API returned status {response.status_code}: {response.text}",
                    student_id=student_id_number,
                )

        except requests.exceptions.Timeout:
            raise StudentVerificationError(
                "Student verification API timeout",
                student_id=student_id_number,
            )
        except requests.exceptions.ConnectionError:
            raise StudentVerificationError(
                "Cannot connect to student verification API",
                student_id=student_id_number,
            )
        except requests.exceptions.RequestException as e:
            raise StudentVerificationError(
                f"API request failed: {str(e)}",
                student_id=student_id_number,
            )

    def _parse_api_response(self, data: Dict[str, Any], student_id_number: str) -> Dict[str, Any]:
        """
        解析API回應並轉換為標準格式
        """
        try:
            # 根據API回應格式解析狀態
            api_status = data.get("status", "").lower()

            if api_status in ["active", "enrolled", "在學"]:
                status = StudentVerificationStatus.VERIFIED
                message = "學籍驗證通過"
            elif api_status in ["graduated", "畢業"]:
                status = StudentVerificationStatus.GRADUATED
                message = "學生已畢業"
            elif api_status in ["suspended", "休學"]:
                status = StudentVerificationStatus.SUSPENDED
                message = "學生目前休學中"
            elif api_status in ["withdrawn", "退學"]:
                status = StudentVerificationStatus.WITHDRAWN
                message = "學生已退學"
            else:
                status = StudentVerificationStatus.NOT_FOUND
                message = "學籍狀態未知"

            return {
                "status": status,
                "message": message,
                "student_info": data.get("student_info", {}),
                "verified_at": datetime.now(),
                "api_response": data,
            }

        except Exception as e:
            logger.error(f"Failed to parse API response for {student_id_number}: {e}")
            return {
                "status": StudentVerificationStatus.API_ERROR,
                "message": f"API回應解析錯誤: {str(e)}",
                "student_info": {},
                "verified_at": datetime.now(),
                "api_response": data,
            }

    def batch_verify_students(self, students: list) -> Dict[str, Dict[str, Any]]:
        """
        批次驗證學生

        Args:
            students: 學生清單 [{"id": str, "name": str}, ...]

        Returns:
            Dict[str, Dict[str, Any]]: 驗證結果字典，key為學生ID
        """
        results = {}

        for student in students:
            student_id = student.get("id") or student.get("student_id")
            student_name = student.get("name") or student.get("student_name")

            if not student_id or not student_name:
                logger.warning(f"Invalid student data: {student}")
                continue

            try:
                result = self.verify_student(student_id, student_name)
                results[student_id] = result
            except Exception as e:
                logger.error(f"Batch verification failed for {student_id}: {e}")
                results[student_id] = {
                    "status": StudentVerificationStatus.API_ERROR,
                    "message": f"批次驗證錯誤: {str(e)}",
                    "student_info": {},
                    "verified_at": datetime.now(),
                    "api_response": {"error": str(e)},
                }

        return results

    def is_verification_available(self) -> bool:
        """
        檢查驗證服務是否可用
        """
        if self.mock_mode:
            return True

        if not self.api_base_url or not self.api_key:
            return False

        try:
            response = self.session.get(
                f"{self.api_base_url}/health",
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_verification_status_label(self, status: StudentVerificationStatus, locale: str = "zh") -> str:
        """
        取得驗證狀態的顯示標籤
        """
        labels = {
            "zh": {
                StudentVerificationStatus.VERIFIED: "已驗證",
                StudentVerificationStatus.GRADUATED: "已畢業",
                StudentVerificationStatus.SUSPENDED: "休學中",
                StudentVerificationStatus.WITHDRAWN: "已退學",
                StudentVerificationStatus.API_ERROR: "驗證錯誤",
                StudentVerificationStatus.NOT_FOUND: "查無此人",
            },
            "en": {
                StudentVerificationStatus.VERIFIED: "Verified",
                StudentVerificationStatus.GRADUATED: "Graduated",
                StudentVerificationStatus.SUSPENDED: "Suspended",
                StudentVerificationStatus.WITHDRAWN: "Withdrawn",
                StudentVerificationStatus.API_ERROR: "API Error",
                StudentVerificationStatus.NOT_FOUND: "Not Found",
            },
        }

        return labels.get(locale, labels["zh"]).get(status, str(status.value))
