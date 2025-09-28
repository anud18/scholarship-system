"""
Test suite for OCR API endpoints
"""

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from PIL import Image

from app.core.exceptions import OCRError
from app.main import app


class TestOCREndpoints:
    """Test OCR API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def sample_image_file(self):
        """Create sample image file for testing"""
        # Create a simple test image
        image = Image.new("RGB", (200, 100), color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        buffer.seek(0)
        return buffer

    @pytest.fixture
    def invalid_file(self):
        """Create invalid file for testing"""
        return io.BytesIO(b"invalid file content")

    @pytest.fixture
    def large_image_file(self):
        """Create large image file for testing"""
        # Create a large image (>10MB)
        large_data = b"fake_large_image_data" * (1024 * 1024)  # ~22MB
        return io.BytesIO(large_data)

    @pytest.fixture
    def mock_current_user(self):
        """Mock current user"""
        user = MagicMock()
        user.id = 1
        user.nycu_id = "test_user"
        return user

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    @patch("app.api.v1.endpoints.user_profiles.get_ocr_service")
    def test_bank_passbook_ocr_success(
        self, mock_get_ocr_service, mock_get_current_user, client, sample_image_file, mock_current_user
    ):
        """Test successful bank passbook OCR"""
        mock_get_current_user.return_value = mock_current_user

        # Mock OCR service
        mock_ocr_service = MagicMock()
        mock_ocr_service.extract_bank_info_from_image = AsyncMock(
            return_value={
                "success": True,
                "bank_name": "台灣銀行",
                "bank_code": "004",
                "account_number": "123456789012",
                "account_holder": "王小明",
                "branch_name": "台北分行",
                "confidence": 0.95,
            }
        )
        mock_get_ocr_service.return_value = mock_ocr_service

        response = client.post(
            "/api/v1/user-profiles/bank-passbook-ocr", files={"file": ("test.jpg", sample_image_file, "image/jpeg")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "銀行資訊提取成功"
        assert data["data"]["bank_name"] == "台灣銀行"
        assert data["data"]["bank_code"] == "004"
        assert data["data"]["account_number"] == "123456789012"

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    @patch("app.api.v1.endpoints.user_profiles.get_ocr_service")
    def test_bank_passbook_ocr_low_confidence(
        self, mock_get_ocr_service, mock_get_current_user, client, sample_image_file, mock_current_user
    ):
        """Test bank passbook OCR with low confidence"""
        mock_get_current_user.return_value = mock_current_user

        # Mock OCR service with low confidence
        mock_ocr_service = MagicMock()
        mock_ocr_service.extract_bank_info_from_image = AsyncMock(
            return_value={
                "success": True,
                "bank_name": "台灣銀行",
                "bank_code": "004",
                "account_number": "123456789012",
                "confidence": 0.7,  # Low confidence
            }
        )
        mock_get_ocr_service.return_value = mock_ocr_service

        response = client.post(
            "/api/v1/user-profiles/bank-passbook-ocr", files={"file": ("test.jpg", sample_image_file, "image/jpeg")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "warning" in data
        assert "信心度較低" in data["warning"]

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    @patch("app.api.v1.endpoints.user_profiles.get_ocr_service")
    def test_bank_passbook_ocr_failure(
        self, mock_get_ocr_service, mock_get_current_user, client, sample_image_file, mock_current_user
    ):
        """Test bank passbook OCR failure"""
        mock_get_current_user.return_value = mock_current_user

        # Mock OCR service failure
        mock_ocr_service = MagicMock()
        mock_ocr_service.extract_bank_info_from_image = AsyncMock(
            return_value={"success": False, "error": "此圖片不是銀行存摺或帳戶資料", "confidence": 0.0}
        )
        mock_get_ocr_service.return_value = mock_ocr_service

        response = client.post(
            "/api/v1/user-profiles/bank-passbook-ocr", files={"file": ("test.jpg", sample_image_file, "image/jpeg")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True  # API call succeeded
        assert data["message"] == "銀行資訊提取失敗"
        assert data["data"]["success"] is False

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    def test_bank_passbook_ocr_invalid_file_type(self, mock_get_current_user, client, mock_current_user):
        """Test bank passbook OCR with invalid file type"""
        mock_get_current_user.return_value = mock_current_user

        text_file = io.BytesIO(b"This is text content")
        response = client.post(
            "/api/v1/user-profiles/bank-passbook-ocr", files={"file": ("test.txt", text_file, "text/plain")}
        )

        assert response.status_code == 400
        assert "File must be an image" in response.json()["detail"]

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    def test_bank_passbook_ocr_file_too_large(self, mock_get_current_user, client, mock_current_user):
        """Test bank passbook OCR with file too large"""
        mock_get_current_user.return_value = mock_current_user

        # Create large file content
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        large_file = io.BytesIO(large_content)

        response = client.post(
            "/api/v1/user-profiles/bank-passbook-ocr", files={"file": ("large.jpg", large_file, "image/jpeg")}
        )

        assert response.status_code == 400
        assert "File size must be less than 10MB" in response.json()["detail"]

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    @patch("app.api.v1.endpoints.user_profiles.get_ocr_service")
    def test_bank_passbook_ocr_service_unavailable(
        self, mock_get_ocr_service, mock_get_current_user, client, sample_image_file, mock_current_user
    ):
        """Test bank passbook OCR when service is unavailable"""
        mock_get_current_user.return_value = mock_current_user
        mock_get_ocr_service.side_effect = OCRError("OCR service is disabled")

        response = client.post(
            "/api/v1/user-profiles/bank-passbook-ocr", files={"file": ("test.jpg", sample_image_file, "image/jpeg")}
        )

        assert response.status_code == 503
        assert "OCR service is not available" in response.json()["detail"]

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    @patch("app.api.v1.endpoints.user_profiles.get_ocr_service")
    def test_bank_passbook_ocr_processing_error(
        self, mock_get_ocr_service, mock_get_current_user, client, sample_image_file, mock_current_user
    ):
        """Test bank passbook OCR processing error"""
        mock_get_current_user.return_value = mock_current_user

        # Mock OCR service processing error
        mock_ocr_service = MagicMock()
        mock_ocr_service.extract_bank_info_from_image = AsyncMock(side_effect=OCRError("Failed to process image"))
        mock_get_ocr_service.return_value = mock_ocr_service

        response = client.post(
            "/api/v1/user-profiles/bank-passbook-ocr", files={"file": ("test.jpg", sample_image_file, "image/jpeg")}
        )

        assert response.status_code == 422
        assert "Failed to process image" in response.json()["detail"]

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    @patch("app.api.v1.endpoints.user_profiles.get_ocr_service")
    def test_document_ocr_success(
        self, mock_get_ocr_service, mock_get_current_user, client, sample_image_file, mock_current_user
    ):
        """Test successful document OCR"""
        mock_get_current_user.return_value = mock_current_user

        # Mock OCR service
        mock_ocr_service = MagicMock()
        mock_ocr_service.extract_general_text_from_image = AsyncMock(
            return_value={"success": True, "extracted_text": "這是測試文件內容\n包含多行文字\n以及一些數字 123456", "confidence": 0.92}
        )
        mock_get_ocr_service.return_value = mock_ocr_service

        response = client.post(
            "/api/v1/user-profiles/document-ocr", files={"file": ("test.jpg", sample_image_file, "image/jpeg")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "文字提取成功"
        assert "這是測試文件內容" in data["data"]["extracted_text"]
        assert data["data"]["confidence"] == 0.92

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    @patch("app.api.v1.endpoints.user_profiles.get_ocr_service")
    def test_document_ocr_failure(
        self, mock_get_ocr_service, mock_get_current_user, client, sample_image_file, mock_current_user
    ):
        """Test document OCR failure"""
        mock_get_current_user.return_value = mock_current_user

        # Mock OCR service failure
        mock_ocr_service = MagicMock()
        mock_ocr_service.extract_general_text_from_image = AsyncMock(
            return_value={"success": False, "error": "無法識別圖片中的文字", "confidence": 0.0}
        )
        mock_get_ocr_service.return_value = mock_ocr_service

        response = client.post(
            "/api/v1/user-profiles/document-ocr", files={"file": ("test.jpg", sample_image_file, "image/jpeg")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True  # API call succeeded
        assert data["message"] == "文字提取失敗"
        assert data["data"]["success"] is False

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    def test_document_ocr_invalid_file_type(self, mock_get_current_user, client, mock_current_user):
        """Test document OCR with invalid file type"""
        mock_get_current_user.return_value = mock_current_user

        text_file = io.BytesIO(b"This is text content")
        response = client.post(
            "/api/v1/user-profiles/document-ocr", files={"file": ("test.txt", text_file, "text/plain")}
        )

        assert response.status_code == 400
        assert "File must be an image" in response.json()["detail"]

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    @patch("app.api.v1.endpoints.user_profiles.get_ocr_service")
    def test_document_ocr_unexpected_error(
        self, mock_get_ocr_service, mock_get_current_user, client, sample_image_file, mock_current_user
    ):
        """Test document OCR unexpected error"""
        mock_get_current_user.return_value = mock_current_user

        # Mock unexpected error
        mock_ocr_service = MagicMock()
        mock_ocr_service.extract_general_text_from_image = AsyncMock(side_effect=Exception("Unexpected error"))
        mock_get_ocr_service.return_value = mock_ocr_service

        response = client.post(
            "/api/v1/user-profiles/document-ocr", files={"file": ("test.jpg", sample_image_file, "image/jpeg")}
        )

        assert response.status_code == 500
        assert "An unexpected error occurred" in response.json()["detail"]

    def test_bank_passbook_ocr_no_auth(self, client, sample_image_file):
        """Test bank passbook OCR without authentication"""
        response = client.post(
            "/api/v1/user-profiles/bank-passbook-ocr", files={"file": ("test.jpg", sample_image_file, "image/jpeg")}
        )

        # Should require authentication
        assert response.status_code == 401 or response.status_code == 403

    def test_document_ocr_no_auth(self, client, sample_image_file):
        """Test document OCR without authentication"""
        response = client.post(
            "/api/v1/user-profiles/document-ocr", files={"file": ("test.jpg", sample_image_file, "image/jpeg")}
        )

        # Should require authentication
        assert response.status_code == 401 or response.status_code == 403

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    def test_bank_passbook_ocr_no_file(self, mock_get_current_user, client, mock_current_user):
        """Test bank passbook OCR without file"""
        mock_get_current_user.return_value = mock_current_user

        response = client.post("/api/v1/user-profiles/bank-passbook-ocr")

        assert response.status_code == 422  # Unprocessable Entity

    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    def test_document_ocr_no_file(self, mock_get_current_user, client, mock_current_user):
        """Test document OCR without file"""
        mock_get_current_user.return_value = mock_current_user

        response = client.post("/api/v1/user-profiles/document-ocr")

        assert response.status_code == 422  # Unprocessable Entity


class TestOCRIntegration:
    """Integration tests for OCR functionality"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @patch("app.services.ocr_service.settings")
    @patch("app.api.v1.endpoints.user_profiles.get_current_user")
    def test_end_to_end_bank_ocr_disabled(self, mock_get_current_user, mock_settings, client):
        """Test end-to-end flow when OCR is disabled"""
        # Mock settings with OCR disabled
        mock_settings.ocr_service_enabled = False

        mock_user = MagicMock()
        mock_user.id = 1
        mock_get_current_user.return_value = mock_user

        # Create sample image
        image = Image.new("RGB", (200, 100), color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        buffer.seek(0)

        response = client.post(
            "/api/v1/user-profiles/bank-passbook-ocr", files={"file": ("test.jpg", buffer, "image/jpeg")}
        )

        assert response.status_code == 503
        assert "OCR service is not available" in response.json()["detail"]
