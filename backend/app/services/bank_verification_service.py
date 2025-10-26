"""
Bank Account Verification Service
Compares user-entered bank information with OCR-extracted data from passbook images
"""

import difflib
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import OCRError
from app.models.application import Application, ApplicationFile
from app.services.ocr_service import get_ocr_service


class BankVerificationService:
    """Service for verifying bank account information against passbook images"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if not text:
            return ""
        # Remove extra spaces, convert to lowercase, remove special characters
        normalized = re.sub(r"[^\w\s]", "", text.lower().strip())
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity score between two texts (0.0 to 1.0)"""
        if not text1 and not text2:
            return 1.0
        if not text1 or not text2:
            return 0.0

        norm1 = self.normalize_text(text1)
        norm2 = self.normalize_text(text2)

        # Use SequenceMatcher for similarity calculation
        similarity = difflib.SequenceMatcher(None, norm1, norm2).ratio()
        return similarity

    def extract_bank_fields_from_application(self, application: Application) -> Dict[str, str]:
        """Extract bank account fields from application form data"""
        bank_fields = {}

        if not application.submitted_form_data or not application.submitted_form_data.get("fields"):
            return bank_fields

        fields = application.submitted_form_data["fields"]

        # Common field mappings (adjust based on your form structure)
        field_mappings = {
            "account_number": ["postal_account", "bank_account", "account_number", "帳戶號碼", "帳號", "郵局帳號"],
            "account_holder": ["account_holder", "account_name", "戶名", "帳戶名稱"],
        }

        for standard_field, possible_keys in field_mappings.items():
            for key in possible_keys:
                if key in fields and fields[key].get("value"):
                    bank_fields[standard_field] = str(fields[key]["value"])
                    break

        # If account_holder not found in form, use applicant's name from student_data
        if "account_holder" not in bank_fields or not bank_fields["account_holder"]:
            if application.student_data and application.student_data.get("std_cname"):
                bank_fields["account_holder"] = application.student_data["std_cname"]

        return bank_fields

    async def get_bank_passbook_document(self, application: Application) -> Optional[ApplicationFile]:
        """Get the bank passbook document from application"""
        if not application.submitted_form_data or not application.submitted_form_data.get("documents"):
            return None

        documents = application.submitted_form_data["documents"]

        # Look for bank account cover document
        for doc in documents:
            # Support both English and Chinese document IDs
            if doc.get("document_id") in ["bank_account_cover", "存摺封面"]:
                # Prefer using file_id for accurate lookup
                file_id = doc.get("file_id")
                if file_id:
                    stmt = select(ApplicationFile).where(
                        ApplicationFile.application_id == application.id, ApplicationFile.id == file_id
                    )
                else:
                    # Fallback: use filename field
                    filename = doc.get("filename") or doc.get("original_filename")
                    if filename:
                        stmt = select(ApplicationFile).where(
                            ApplicationFile.application_id == application.id, ApplicationFile.filename == filename
                        )
                    else:
                        continue

                result = await self.db.execute(stmt)
                passbook_file = result.scalar_one_or_none()
                if passbook_file:
                    return passbook_file

        return None

    async def verify_bank_account(self, application_id: int) -> Dict[str, Any]:
        """
        Verify bank account information by comparing form data with OCR results

        Returns:
            Dict containing verification results with detailed comparison
        """
        # Get application
        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise ValueError(f"Application with ID {application_id} not found")

        # Extract bank fields from application form
        form_bank_fields = self.extract_bank_fields_from_application(application)

        if not form_bank_fields:
            return {
                "success": False,
                "error": "No bank account information found in application form",
                "application_id": application_id,
                "verification_status": "no_data",
            }

        # Get bank passbook document
        passbook_doc = await self.get_bank_passbook_document(application)

        if not passbook_doc:
            return {
                "success": False,
                "error": "No bank passbook document found in application",
                "application_id": application_id,
                "form_data": form_bank_fields,
                "verification_status": "no_document",
            }

        # Perform OCR on passbook document
        try:
            # Get MinIO service to read file
            from app.services.minio_service import get_minio_service

            minio_service = get_minio_service()

            # Initialize OCR service
            ocr_service = get_ocr_service(self.db)

            # Validate that object_name exists
            if not passbook_doc.object_name:
                raise OCRError("File object_name is missing in database")

            # Read file from MinIO
            try:
                file_stream = minio_service.get_file_stream(passbook_doc.object_name)
                image_data = file_stream.read()
                file_stream.close()
                file_stream.release_conn()
            except Exception as e:
                raise OCRError(f"Failed to read file from storage: {str(e)}")

            # Perform OCR extraction
            ocr_result = await ocr_service.extract_bank_info_from_image(image_data=image_data, db=self.db)

            # Validate OCR result
            if not ocr_result.get("success"):
                raise OCRError(ocr_result.get("error", "OCR extraction returned unsuccessful result"))

        except OCRError as e:
            return {
                "success": False,
                "error": f"OCR processing failed: {str(e)}",
                "application_id": application_id,
                "form_data": form_bank_fields,
                "verification_status": "ocr_failed",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error during OCR: {str(e)}",
                "application_id": application_id,
                "form_data": form_bank_fields,
                "verification_status": "ocr_failed",
            }

        # Compare fields
        comparisons = {}
        overall_match = True
        total_confidence = 0.0
        compared_fields = 0

        field_mappings = {
            "account_number": "郵局帳號",
            "account_holder": "戶名",
        }

        for field_key, field_name in field_mappings.items():
            form_value = form_bank_fields.get(field_key, "")
            ocr_value = ocr_result.get(field_key, "")

            if form_value or ocr_value:
                similarity = self.calculate_similarity(form_value, ocr_value)
                is_match = similarity >= 0.8  # 80% similarity threshold

                comparisons[field_key] = {
                    "field_name": field_name,
                    "form_value": form_value,
                    "ocr_value": ocr_value,
                    "similarity_score": round(similarity, 3),
                    "is_match": is_match,
                    "confidence": "high" if similarity >= 0.9 else "medium" if similarity >= 0.7 else "low",
                }

                if not is_match:
                    overall_match = False

                total_confidence += similarity
                compared_fields += 1

        # Calculate overall confidence
        average_confidence = total_confidence / compared_fields if compared_fields > 0 else 0.0

        # Determine verification status
        if overall_match and average_confidence >= 0.9:
            verification_status = "verified"
        elif overall_match and average_confidence >= 0.7:
            verification_status = "likely_verified"
        elif compared_fields == 0:
            verification_status = "no_comparison"
        else:
            verification_status = "verification_failed"

        return {
            "success": True,
            "application_id": application_id,
            "verification_status": verification_status,
            "overall_match": overall_match,
            "average_confidence": round(average_confidence, 3),
            "compared_fields": compared_fields,
            "comparisons": comparisons,
            "form_data": form_bank_fields,
            "ocr_data": {k: v for k, v in ocr_result.items() if k not in ["success"]},
            "passbook_document": {
                "file_path": passbook_doc.filename,
                "original_filename": passbook_doc.original_filename,
                "upload_time": passbook_doc.uploaded_at.isoformat() if passbook_doc.uploaded_at else None,
            },
            "recommendations": self.generate_recommendations(verification_status, comparisons),
        }

    def generate_recommendations(self, status: str, comparisons: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on verification results"""
        recommendations = []

        if status == "verified":
            recommendations.append("✅ 郵局帳號資訊驗證通過，資料一致性良好")
        elif status == "likely_verified":
            recommendations.append("⚠️ 郵局帳號資訊基本一致，建議人工核對細節")
        elif status == "verification_failed":
            recommendations.append("❌ 郵局帳號資訊不一致，需要人工審核")

            # Add specific field recommendations
            for field_key, comparison in comparisons.items():
                if not comparison["is_match"]:
                    recommendations.append(
                        f"• {comparison['field_name']}: 表單填寫「{comparison['form_value']}」"
                        f"與存摺顯示「{comparison['ocr_value']}」不符"
                    )

        if any(comp["confidence"] == "low" for comp in comparisons.values()):
            recommendations.append("⚠️ 部分欄位OCR信心度較低，建議人工確認")

        return recommendations

    async def get_verification_history(self, application_id: int) -> List[Dict[str, Any]]:
        """Get verification history for an application from audit logs"""
        from app.services.application_audit_service import ApplicationAuditService

        audit_service = ApplicationAuditService(self.db)

        # Get all bank verification audit logs for this application
        audit_logs = await audit_service.get_application_audit_trail(
            application_id=application_id,
            action_filter="verify_bank_account",  # Only bank verification logs
            limit=100,  # Get up to 100 verification records
        )

        # Convert audit logs to verification history format
        history = []
        for log in audit_logs:
            history_entry = {
                "timestamp": log.created_at.isoformat() if log.created_at else None,
                "verified_by_user_id": log.user_id,
                "verified_by_username": log.user.nycu_id if log.user else "Unknown",
                "verified_by_name": log.user.name if log.user else "Unknown",
                "verification_status": log.meta_data.get("verification_status") if log.meta_data else None,
                "overall_match": log.meta_data.get("overall_match") if log.meta_data else None,
                "average_confidence": log.meta_data.get("average_confidence") if log.meta_data else None,
                "compared_fields": log.meta_data.get("compared_fields") if log.meta_data else None,
                "description": log.description,
                "status": log.status,
                "error_message": log.error_message,
                "ip_address": log.ip_address,
            }
            history.append(history_entry)

        return history

    async def batch_verify_applications(self, application_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Verify multiple applications in batch"""
        results = {}

        for app_id in application_ids:
            try:
                result = await self.verify_bank_account(app_id)
                results[app_id] = result
            except Exception as e:
                results[app_id] = {
                    "success": False,
                    "error": str(e),
                    "application_id": app_id,
                    "verification_status": "error",
                }

        return results
