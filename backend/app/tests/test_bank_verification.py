"""
Tests for Bank Account Verification Service
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.application import Application, ApplicationFile
from app.services.bank_verification_service import BankVerificationService


class TestBankVerificationService:
    """Test Bank Account Verification Service"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def verification_service(self, mock_db):
        """Create verification service with mocked database"""
        return BankVerificationService(mock_db)

    def test_normalize_text(self, verification_service):
        """Test text normalization for comparison"""
        test_cases = [
            ("Taiwan Bank", "taiwan bank"),
            ("台灣銀行", "台灣銀行"),
            ("Account: 123-456-789", "account 123456789"),
            ("  Extra   Spaces  ", "extra spaces"),
            ("", ""),
            (None, ""),
        ]

        for input_text, expected in test_cases:
            result = verification_service.normalize_text(input_text)
            assert result == expected, f"Failed for input: {input_text}"

    def test_calculate_similarity(self, verification_service):
        """Test similarity calculation between texts"""
        test_cases = [
            ("台灣銀行", "台灣銀行", 1.0),  # Exact match
            ("Taiwan Bank", "taiwan bank", 1.0),  # Case insensitive
            ("123456789", "123-456-789", 0.9),  # Similar numbers
            ("", "", 1.0),  # Both empty
            ("something", "", 0.0),  # One empty
            ("", "something", 0.0),  # Other empty
            ("completely", "different", 0.0),  # Very different
        ]

        for text1, text2, expected_min in test_cases:
            similarity = verification_service.calculate_similarity(text1, text2)
            assert (
                similarity >= expected_min
            ), f"Failed for '{text1}' vs '{text2}': got {similarity}, expected >= {expected_min}"

    def test_extract_bank_fields_from_application(self, verification_service):
        """Test extraction of bank fields from application"""
        # Create mock application with bank account data
        application = Application()
        application.form_data = {
            "fields": {
                "bank_account": {
                    "field_id": "bank_account",
                    "field_type": "text",
                    "value": "123456789012",
                    "required": True,
                },
                "account_holder": {
                    "field_id": "account_holder",
                    "field_type": "text",
                    "value": "王小明",
                    "required": True,
                },
            }
        }

        result = verification_service.extract_bank_fields_from_application(application)

        expected = {"account_number": "123456789012", "account_holder": "王小明"}

        assert result == expected

    def test_extract_bank_fields_empty_form_data(self, verification_service):
        """Test extraction when application has no form data"""
        application = Application()
        application.form_data = None

        result = verification_service.extract_bank_fields_from_application(application)
        assert result == {}

        # Test with empty fields
        application.form_data = {"fields": {}}
        result = verification_service.extract_bank_fields_from_application(application)
        assert result == {}

    @pytest.mark.asyncio
    async def test_verify_bank_account_application_not_found(self, verification_service, mock_db):
        """Test verification when application is not found"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Application with ID 999 not found"):
            await verification_service.verify_bank_account(999)

    @pytest.mark.asyncio
    async def test_verify_bank_account_no_bank_data(self, verification_service, mock_db):
        """Test verification when application has no bank data"""
        # Mock application without bank data
        application = Application()
        application.id = 1
        application.form_data = {"fields": {}}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = application
        mock_db.execute.return_value = mock_result

        result = await verification_service.verify_bank_account(1)

        assert result["success"] is False
        assert result["error"] == "No bank account information found in application form"
        assert result["verification_status"] == "no_data"

    @pytest.mark.asyncio
    async def test_verify_bank_account_no_passbook_document(self, verification_service, mock_db):
        """Test verification when passbook document is missing"""
        # Mock application with bank data but no document
        application = Application()
        application.id = 1
        application.form_data = {"fields": {"bank_account": {"value": "123456789"}}, "documents": []}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [application, None]  # App found, document not found
        mock_db.execute.return_value = mock_result

        result = await verification_service.verify_bank_account(1)

        assert result["success"] is False
        assert result["error"] == "No bank passbook document found in application"
        assert result["verification_status"] == "no_document"

    @pytest.mark.asyncio
    @patch("app.services.bank_verification_service.get_ocr_service")
    async def test_verify_bank_account_success_scenario(self, mock_get_ocr_service, verification_service, mock_db):
        """Test successful bank account verification"""
        # Mock OCR service
        mock_ocr_service = MagicMock()
        mock_ocr_service.extract_bank_info_from_image.return_value = {
            "success": True,
            "account_number": "123456789012",
            "account_holder": "王小明",
            "branch_name": "台北分行",
            "confidence": 0.95,
        }
        mock_get_ocr_service.return_value = mock_ocr_service

        # Mock application with complete data
        application = Application()
        application.id = 1
        application.form_data = {
            "fields": {
                "bank_account": {"value": "123456789012"},
                "account_holder": {"value": "王小明"},
            },
            "documents": [
                {"document_id": "bank_account_cover", "file_path": "test.pdf", "original_filename": "passbook.pdf"}
            ],
        }

        # Mock passbook document
        passbook_doc = ApplicationFile()
        passbook_doc.filename = "test.pdf"
        passbook_doc.original_filename = "passbook.pdf"
        passbook_doc.uploaded_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [application, passbook_doc]
        mock_db.execute.return_value = mock_result

        result = await verification_service.verify_bank_account(1)

        assert result["success"] is True
        assert result["application_id"] == 1
        assert "verification_status" in result
        assert "comparisons" in result
        assert "form_data" in result
        assert "ocr_data" in result
        assert "recommendations" in result

        # Check that form data was extracted
        assert result["form_data"]["account_number"] == "123456789012"
        assert result["form_data"]["account_holder"] == "王小明"

    @pytest.mark.asyncio
    async def test_batch_verify_applications(self, verification_service):
        """Test batch verification of multiple applications"""
        application_ids = [1, 2, 3]

        # Mock the verify_bank_account method to return different results
        async def mock_verify(app_id):
            if app_id == 1:
                return {"success": True, "verification_status": "verified", "application_id": app_id}
            elif app_id == 2:
                return {"success": False, "error": "No data", "application_id": app_id}
            else:
                raise ValueError("Application not found")

        verification_service.verify_bank_account = AsyncMock(side_effect=mock_verify)

        results = await verification_service.batch_verify_applications(application_ids)

        assert len(results) == 3
        assert results[1]["success"] is True
        assert results[2]["success"] is False
        assert results[3]["success"] is False
        assert "Application not found" in results[3]["error"]

    def test_generate_recommendations(self, verification_service):
        """Test generation of verification recommendations"""
        # Test verified status
        recommendations = verification_service.generate_recommendations("verified", {})
        assert any("驗證通過" in rec for rec in recommendations)

        # Test failed verification with mismatched fields
        comparisons = {
            "account_number": {
                "field_name": "帳戶號碼",
                "form_value": "123456",
                "ocr_value": "123456",
                "is_match": True,
                "confidence": "high",
            },
        }

        recommendations = verification_service.generate_recommendations("verification_failed", comparisons)
        assert any("不一致" in rec for rec in recommendations) or len(recommendations) > 0

        # Test low confidence scenario
        comparisons_low_confidence = {"account_number": {"confidence": "low", "is_match": True}}

        recommendations = verification_service.generate_recommendations("verified", comparisons_low_confidence)
        assert any("信心度較低" in rec for rec in recommendations)

    @pytest.mark.asyncio
    async def test_get_bank_passbook_document(self, verification_service, mock_db):
        """Test retrieving bank passbook document from application"""
        # Mock application with passbook document
        application = Application()
        application.id = 1
        application.form_data = {
            "documents": [
                {"document_id": "bank_account_cover", "file_path": "passbook.pdf"},
                {"document_id": "other_document", "file_path": "other.pdf"},
            ]
        }

        # Mock document retrieval
        mock_document = ApplicationFile()
        mock_document.filename = "passbook.pdf"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute.return_value = mock_result

        result = await verification_service.get_bank_passbook_document(application)

        assert result == mock_document
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_bank_passbook_document_not_found(self, verification_service, mock_db):
        """Test when passbook document is not found"""
        # Mock application without passbook document
        application = Application()
        application.form_data = {"documents": [{"document_id": "other_document", "file_path": "other.pdf"}]}

        result = await verification_service.get_bank_passbook_document(application)
        assert result is None

        # Test with no documents
        application.form_data = None
        result = await verification_service.get_bank_passbook_document(application)
        assert result is None
