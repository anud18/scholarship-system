"""
Test suite for OCR Service using Google Gemini API
"""

import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.core.exceptions import OCRError
from app.services.ocr_service import OCRService, get_ocr_service


class TestOCRService:
    """Test OCR Service functionality"""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for OCR service"""
        return SimpleNamespace(
            ocr_service_enabled=True, gemini_api_key="test-api-key", gemini_model="gemini-2.0-flash", ocr_timeout=30
        )

    @pytest.fixture
    def sample_image_bytes(self):
        """Create sample image bytes for testing"""
        # Create a simple test image
        image = Image.new("RGB", (200, 100), color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return buffer.getvalue()

    @pytest.fixture
    def invalid_image_bytes(self):
        """Create invalid image data for testing"""
        return b"invalid image data"

    @pytest.fixture
    def small_image_bytes(self):
        """Create image that's too small for OCR"""
        image = Image.new("RGB", (50, 50), color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return buffer.getvalue()

    @patch("app.services.ocr_service.settings")
    @patch("app.services.ocr_service.genai")
    def test_ocr_service_initialization_success(self, mock_genai, mock_settings):
        """Test successful OCR service initialization"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"

        # Mock the GenerativeModel
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        service = OCRService()

        mock_genai.configure.assert_called_once_with(api_key="test-key")
        mock_genai.GenerativeModel.assert_called_once_with("gemini-2.0-flash")
        assert service.model == mock_model

    @patch("app.services.ocr_service.settings")
    def test_ocr_service_initialization_disabled(self, mock_settings):
        """Test OCR service initialization when disabled"""
        mock_settings.ocr_service_enabled = False

        with pytest.raises(OCRError, match="OCR service is disabled"):
            OCRService()

    @patch("app.services.ocr_service.settings")
    def test_ocr_service_initialization_no_api_key(self, mock_settings):
        """Test OCR service initialization without API key"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = None

        with pytest.raises(OCRError, match="Gemini API key is not configured"):
            OCRService()

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.settings")
    @patch("app.services.ocr_service.genai")
    async def test_extract_bank_info_success(self, mock_genai, mock_settings, sample_image_bytes):
        """Test successful bank information extraction"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"

        # Mock successful response
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "success": True,
                "account_number": "123456789012",
                "account_holder": "王小明",
                "branch_name": "台北分行",
                "confidence": 0.95,
            }
        )

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        service = OCRService()
        result = await service.extract_bank_info_from_image(sample_image_bytes)

        assert result["success"] is True
        assert result["account_number"] == "123456789012"
        assert result["account_holder"] == "王小明"
        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.settings")
    @patch("app.services.ocr_service.genai")
    async def test_extract_bank_info_failure(self, mock_genai, mock_settings, sample_image_bytes):
        """Test bank information extraction failure"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"

        # Mock failure response
        mock_response = MagicMock()
        mock_response.text = json.dumps({"success": False, "error": "此圖片不是銀行存摺或帳戶資料", "confidence": 0.0})

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        service = OCRService()
        result = await service.extract_bank_info_from_image(sample_image_bytes)

        assert result["success"] is False
        assert "此圖片不是銀行存摺" in result["error"]
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.settings")
    @patch("app.services.ocr_service.genai")
    async def test_extract_general_text_success(self, mock_genai, mock_settings, sample_image_bytes):
        """Test successful general text extraction"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"

        # Mock successful response
        mock_response = MagicMock()
        mock_response.text = json.dumps({"success": True, "extracted_text": "這是測試文件內容", "confidence": 0.92})

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        service = OCRService()
        result = await service.extract_general_text_from_image(sample_image_bytes)

        assert result["success"] is True
        assert result["extracted_text"] == "這是測試文件內容"
        assert result["confidence"] == 0.92

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.settings")
    @patch("app.services.ocr_service.genai")
    async def test_invalid_image_handling(self, mock_genai, mock_settings, invalid_image_bytes):
        """Test handling of invalid image data"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"

        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        service = OCRService()

        with pytest.raises(OCRError, match="Invalid image format"):
            await service.extract_bank_info_from_image(invalid_image_bytes)

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.settings")
    @patch("app.services.ocr_service.genai")
    async def test_small_image_handling(self, mock_genai, mock_settings, small_image_bytes):
        """Test handling of images that are too small"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"

        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        service = OCRService()

        with pytest.raises(OCRError, match="Image is too small for OCR processing"):
            await service.extract_bank_info_from_image(small_image_bytes)

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.settings")
    @patch("app.services.ocr_service.genai")
    async def test_large_image_resizing(self, mock_genai, mock_settings):
        """Test automatic resizing of large images"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"

        # Create large image
        large_image = Image.new("RGB", (5000, 5000), color="white")
        buffer = io.BytesIO()
        large_image.save(buffer, format="JPEG")
        large_image_bytes = buffer.getvalue()

        # Mock successful response
        mock_response = MagicMock()
        mock_response.text = json.dumps({"success": True, "account_number": "測試帳號", "confidence": 0.9})

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        service = OCRService()
        result = await service.extract_bank_info_from_image(large_image_bytes)

        # Should succeed even with large image (gets resized)
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.settings")
    @patch("app.services.ocr_service.genai")
    async def test_invalid_json_response_handling(self, mock_genai, mock_settings, sample_image_bytes):
        """Test handling of invalid JSON response from Gemini"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"

        # Mock invalid JSON response
        mock_response = MagicMock()
        mock_response.text = "invalid json response"

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        service = OCRService()
        result = await service.extract_bank_info_from_image(sample_image_bytes)

        assert result["success"] is False
        assert "Invalid response format" in result["error"]
        assert result["confidence"] == 0.0
        assert result["raw_response"] == "invalid json response"

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.settings")
    @patch("app.services.ocr_service.genai")
    async def test_markdown_json_response_parsing(self, mock_genai, mock_settings, sample_image_bytes):
        """Test parsing of JSON response wrapped in markdown code blocks"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"

        # Mock response with markdown formatting
        mock_response = MagicMock()
        mock_response.text = '```json\n{"success": true, "account_number": "測試帳號", "confidence": 0.9}\n```'

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        service = OCRService()
        result = await service.extract_bank_info_from_image(sample_image_bytes)

        assert result["success"] is True
        assert result["account_number"] == "測試帳號"
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    @patch("app.services.ocr_service.settings")
    @patch("app.services.ocr_service.genai")
    async def test_gemini_api_exception_handling(self, mock_genai, mock_settings, sample_image_bytes):
        """Test handling of Gemini API exceptions"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gemini_model = "gemini-2.0-flash"

        # Mock API exception
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API connection failed")
        mock_genai.GenerativeModel.return_value = mock_model

        service = OCRService()

        with pytest.raises(OCRError, match="Failed to extract bank information"):
            await service.extract_bank_info_from_image(sample_image_bytes)

    @patch("app.services.ocr_service.settings")
    def test_is_enabled_true(self, mock_settings):
        """Test is_enabled returns True when properly configured"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = "test-key"

        with patch("app.services.ocr_service.genai"):
            service = OCRService()
            assert service.is_enabled() is True

    @patch("app.services.ocr_service.settings")
    def test_is_enabled_false_disabled(self, mock_settings):
        """Test is_enabled returns False when service is disabled"""
        mock_settings.ocr_service_enabled = False
        mock_settings.gemini_api_key = "test-key"

        with patch("app.services.ocr_service.genai"):
            with pytest.raises(OCRError):
                OCRService()

    @patch("app.services.ocr_service.settings")
    def test_is_enabled_false_no_key(self, mock_settings):
        """Test is_enabled returns False when API key is missing"""
        mock_settings.ocr_service_enabled = True
        mock_settings.gemini_api_key = None

        with patch("app.services.ocr_service.genai"):
            with pytest.raises(OCRError):
                OCRService()


class TestOCRServiceSingleton:
    """Test OCR service singleton functionality"""

    @patch("app.services.ocr_service.OCRService")
    def test_get_ocr_service_creates_instance(self, mock_ocr_class):
        """Test that get_ocr_service creates a new instance"""
        # Reset the global instance
        import app.services.ocr_service

        app.services.ocr_service.ocr_service = None

        mock_instance = MagicMock()
        mock_ocr_class.return_value = mock_instance

        result = get_ocr_service()

        mock_ocr_class.assert_called_once()
        assert result == mock_instance

    @patch("app.services.ocr_service.OCRService")
    def test_get_ocr_service_returns_existing_instance(self, mock_ocr_class):
        """Test that get_ocr_service returns existing instance"""
        # Set up existing instance
        import app.services.ocr_service

        existing_instance = MagicMock()
        app.services.ocr_service.ocr_service = existing_instance

        result = get_ocr_service()

        # Should not create new instance
        mock_ocr_class.assert_not_called()
        assert result == existing_instance
