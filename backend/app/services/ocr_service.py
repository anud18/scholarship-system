"""
OCR Service using Google Gemini API
Handles bank passbook and document text extraction
"""

import io
import logging
from typing import Any, Dict, Optional

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from PIL import Image

from app.core.config import settings
from app.core.exceptions import OCRError

logger = logging.getLogger(__name__)


class OCRService:
    """Service for OCR using Google Gemini API"""

    def __init__(self):
        """Initialize OCR service with Gemini API"""
        if not settings.ocr_service_enabled:
            raise OCRError("OCR service is disabled")

        if not settings.gemini_api_key:
            raise OCRError("Gemini API key is not configured")

        if genai is None:
            raise OCRError("Google Generative AI library is not installed. Run: pip install google-generativeai")

        # Configure Gemini API
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(settings.gemini_model)

    async def extract_bank_info_from_image(self, image_data: bytes) -> Dict[str, Any]:
        """
        Extract bank account information from passbook image

        Args:
            image_data: Raw image bytes

        Returns:
            Dict containing extracted bank information
        """
        try:
            # Validate and process image
            image = self._validate_and_process_image(image_data)

            # Define the extraction prompt
            prompt = """
            請從這個銀行存摺或帳戶資料圖片中提取以下資訊：

            1. 銀行名稱 (Bank Name)
            2. 銀行代碼 (Bank Code) - 通常是3位數字
            3. 帳戶號碼 (Account Number) - 完整的帳戶號碼
            4. 帳戶名稱 (Account Holder Name) - 戶名
            5. 分行名稱 (Branch Name) - 如果有的話

            請以以下JSON格式回傳，確保數字和文字準確：
            {
                "success": true,
                "bank_name": "銀行名稱",
                "bank_code": "銀行代碼",
                "account_number": "帳戶號碼",
                "account_holder": "戶名",
                "branch_name": "分行名稱",
                "confidence": 0.95
            }

            如果無法清楚識別某些資訊，請將該欄位設為 null，並調整 confidence 分數。
            如果圖片不是銀行相關文件，請回傳：
            {
                "success": false,
                "error": "此圖片不是銀行存摺或帳戶資料",
                "confidence": 0.0
            }
            """

            # Send request to Gemini
            response = self.model.generate_content([prompt, image])

            # Parse response
            result = self._parse_gemini_response(response.text)

            logger.info(f"Bank OCR extraction completed with confidence: {result.get('confidence', 0)}")
            return result

        except Exception as e:
            logger.error(f"Bank OCR extraction failed: {str(e)}")
            raise OCRError(f"Failed to extract bank information: {str(e)}")

    async def extract_general_text_from_image(self, image_data: bytes) -> Dict[str, Any]:
        """
        Extract general text from any document image

        Args:
            image_data: Raw image bytes

        Returns:
            Dict containing extracted text
        """
        try:
            # Validate and process image
            image = self._validate_and_process_image(image_data)

            # Define the extraction prompt
            prompt = """
            請從這個圖片中提取所有可見的文字內容。
            保持原始格式和結構，包括：
            - 標題和段落
            - 表格數據
            - 數字和日期
            - 任何可見的文字

            請以以下JSON格式回傳：
            {
                "success": true,
                "extracted_text": "提取的完整文字內容",
                "confidence": 0.95
            }

            如果無法識別任何文字，請回傳：
            {
                "success": false,
                "error": "無法識別圖片中的文字",
                "confidence": 0.0
            }
            """

            # Send request to Gemini
            response = self.model.generate_content([prompt, image])

            # Parse response
            result = self._parse_gemini_response(response.text)

            logger.info(f"General OCR extraction completed with confidence: {result.get('confidence', 0)}")
            return result

        except Exception as e:
            logger.error(f"General OCR extraction failed: {str(e)}")
            raise OCRError(f"Failed to extract text: {str(e)}")

    def _validate_and_process_image(self, image_data: bytes) -> Image.Image:
        """Validate and process image for OCR"""
        try:
            # Open image
            image = Image.open(io.BytesIO(image_data))

            # Convert to RGB if necessary
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Validate image size
            width, height = image.size
            if width < 100 or height < 100:
                raise OCRError("Image is too small for OCR processing")

            if width > 4096 or height > 4096:
                # Resize large images
                image.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
                logger.info(f"Resized image from {width}x{height} to {image.size}")

            return image

        except Exception as e:
            raise OCRError(f"Invalid image format: {str(e)}")

    def _parse_gemini_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Gemini API response and extract JSON"""
        import json

        try:
            # Clean up response text (remove markdown formatting if present)
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()

            # Parse JSON
            result = json.loads(cleaned_text)

            # Validate required fields
            if not isinstance(result, dict):
                raise ValueError("Response is not a valid JSON object")

            if "success" not in result:
                raise ValueError("Response missing 'success' field")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {response_text}")
            return {
                "success": False,
                "error": f"Invalid response format: {str(e)}",
                "confidence": 0.0,
                "raw_response": response_text,
            }
        except Exception as e:
            logger.error(f"Error processing Gemini response: {str(e)}")
            return {"success": False, "error": f"Response processing error: {str(e)}", "confidence": 0.0}

    def is_enabled(self) -> bool:
        """Check if OCR service is enabled and configured"""
        return settings.ocr_service_enabled and settings.gemini_api_key is not None


# Global OCR service instance
ocr_service: Optional[OCRService] = None


def get_ocr_service() -> OCRService:
    """Get or create OCR service instance"""
    global ocr_service

    if ocr_service is None:
        ocr_service = OCRService()

    return ocr_service
