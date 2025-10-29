"""
Bank Account Verification Service
Compares user-entered bank information with OCR-extracted data from passbook images
"""

import copy
import difflib
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import OCRError
from app.models.application import Application, ApplicationFile
from app.models.payment_roster import PaymentRosterItem
from app.models.student_bank_account import StudentBankAccount
from app.services.ocr_service import get_ocr_service

# Verification thresholds and constants
ACCOUNT_NUMBER_EXACT_MATCH_REQUIRED = True  # Account number must match 100%
ACCOUNT_HOLDER_SIMILARITY_THRESHOLD = 0.8  # Account holder name similarity threshold
HIGH_CONFIDENCE_THRESHOLD = 0.9  # Above this = auto verify (high confidence)
LOW_CONFIDENCE_THRESHOLD = 0.7  # Below this = needs manual review (low confidence)


class BankVerificationService:
    """Service for verifying bank account information against passbook images"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def validate_postal_account_format(self, account_number: str) -> tuple[bool, Optional[str]]:
        """
        Validate postal account number format

        Taiwanese postal accounts should be 14 digits (format: 7 digits + 7 digits)

        Returns:
            tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if not account_number:
            return False, "帳號不可為空"

        # Remove all non-digit characters (spaces, dashes, etc.)
        cleaned = re.sub(r"\D", "", account_number)

        # Check if it's exactly 14 digits
        if len(cleaned) != 14:
            return False, f"郵局帳號必須為 14 位數字，目前為 {len(cleaned)} 位"

        # Check if all characters are digits
        if not cleaned.isdigit():
            return False, "郵局帳號只能包含數字"

        return True, None

    def normalize_account_number(self, account: str) -> str:
        """
        Normalize account number by removing all non-digit characters

        Args:
            account: Account number string (may contain spaces, dashes, etc.)

        Returns:
            Normalized account number with only digits
        """
        if not account:
            return ""
        return re.sub(r"[^0-9]", "", account)

    def verify_account_number_exact(self, form_value: str, ocr_value: str) -> Dict[str, Any]:
        """
        Verify account number with exact match requirement (100%)

        Args:
            form_value: Account number from application form
            ocr_value: Account number extracted from OCR

        Returns:
            Dict with match result and details
        """
        normalized_form = self.normalize_account_number(form_value)
        normalized_ocr = self.normalize_account_number(ocr_value)

        is_match = normalized_form == normalized_ocr

        return {
            "is_match": is_match,
            "normalized_form": normalized_form,
            "normalized_ocr": normalized_ocr,
            "exact_match_required": ACCOUNT_NUMBER_EXACT_MATCH_REQUIRED,
        }

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

        # Compare fields with separate status tracking
        comparisons = {}
        overall_match = True
        total_confidence = 0.0
        compared_fields = 0

        # Separate status for account number and holder
        account_number_status = "unknown"
        account_holder_status = "unknown"
        requires_manual_review = False

        field_mappings = {
            "account_number": "郵局帳號",
            "account_holder": "戶名",
        }

        for field_key, field_name in field_mappings.items():
            form_value = form_bank_fields.get(field_key, "")
            ocr_value = ocr_result.get(field_key, "")

            # Set status to no_data if both values are missing
            if not form_value and not ocr_value:
                if field_key == "account_number":
                    account_number_status = "no_data"
                elif field_key == "account_holder":
                    account_holder_status = "no_data"
                continue

            if form_value or ocr_value:
                # Different verification logic for account number vs account holder
                if field_key == "account_number":
                    # Account number: 100% exact match required
                    account_result = self.verify_account_number_exact(form_value, ocr_value)
                    is_match = account_result["is_match"]
                    similarity = 1.0 if is_match else 0.0
                    confidence_level = "high" if is_match else "low"
                    needs_manual_review = not is_match

                    comparisons[field_key] = {
                        "field_name": field_name,
                        "form_value": form_value,
                        "ocr_value": ocr_value,
                        "normalized_form": account_result["normalized_form"],
                        "normalized_ocr": account_result["normalized_ocr"],
                        "similarity_score": similarity,
                        "is_match": is_match,
                        "confidence": confidence_level,
                        "needs_manual_review": needs_manual_review,
                        "exact_match_required": True,
                        "manual_review_status": "pending" if needs_manual_review else None,
                        "manual_review_corrected_value": None,
                    }

                    # Set account number status
                    if is_match:
                        account_number_status = "verified"
                    else:
                        account_number_status = "needs_review"
                        requires_manual_review = True
                        overall_match = False

                    total_confidence += similarity
                    compared_fields += 1

                elif field_key == "account_holder":
                    # Account holder: Fuzzy match allowed (80% threshold)
                    similarity = self.calculate_similarity(form_value, ocr_value)
                    is_match = similarity >= ACCOUNT_HOLDER_SIMILARITY_THRESHOLD
                    confidence_level = (
                        "high"
                        if similarity >= HIGH_CONFIDENCE_THRESHOLD
                        else "medium"
                        if similarity >= LOW_CONFIDENCE_THRESHOLD
                        else "low"
                    )
                    needs_manual_review = similarity < LOW_CONFIDENCE_THRESHOLD or not is_match

                    comparisons[field_key] = {
                        "field_name": field_name,
                        "form_value": form_value,
                        "ocr_value": ocr_value,
                        "similarity_score": round(similarity, 3),
                        "is_match": is_match,
                        "confidence": confidence_level,
                        "needs_manual_review": needs_manual_review,
                        "exact_match_required": False,
                        "manual_review_status": "pending" if needs_manual_review else None,
                        "manual_review_corrected_value": None,
                    }

                    # Set account holder status
                    if is_match and confidence_level == "high":
                        account_holder_status = "verified"
                    elif needs_manual_review:
                        account_holder_status = "needs_review"
                        requires_manual_review = True
                    else:
                        account_holder_status = "failed"
                        overall_match = False

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

        # Update application meta_data with separate statuses
        from datetime import datetime, timezone

        application.meta_data = application.meta_data or {}
        application.meta_data["bank_verification"] = {
            "overall_status": verification_status,
            "account_number_status": account_number_status,
            "account_holder_status": account_holder_status,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "requires_manual_review": requires_manual_review,
        }
        await self.db.commit()
        await self.db.refresh(application)

        return {
            "success": True,
            "application_id": application_id,
            "verification_status": verification_status,
            "account_number_status": account_number_status,
            "account_holder_status": account_holder_status,
            "requires_manual_review": requires_manual_review,
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
                "file_id": passbook_doc.id,
                "object_name": passbook_doc.object_name,
            },
            "recommendations": self.generate_recommendations(
                verification_status, comparisons, account_number_status, account_holder_status
            ),
        }

    def generate_recommendations(
        self, status: str, comparisons: Dict[str, Any], account_number_status: str, account_holder_status: str
    ) -> List[str]:
        """Generate recommendations based on verification results"""
        recommendations = []

        # Overall status
        if status == "verified":
            recommendations.append("✅ 郵局帳號資訊驗證通過，資料一致性良好")
        elif status == "likely_verified":
            recommendations.append("⚠️ 郵局帳號資訊基本一致，建議人工核對細節")
        elif status == "verification_failed":
            recommendations.append("❌ 郵局帳號資訊不一致，需要人工審核")

        # Individual field status
        account_number_comp = comparisons.get("account_number", {})
        if account_number_status == "verified":
            recommendations.append("✅ 帳號: 通過")
        elif account_number_status == "needs_review":
            recommendations.append(
                f"⚠️ 帳號: 需人工檢閱 (表單:「{account_number_comp.get('form_value', '')}」 vs OCR:「{account_number_comp.get('ocr_value', '')}」)"
            )
        elif account_number_status == "failed":
            recommendations.append(
                f"❌ 帳號: 不通過 (表單:「{account_number_comp.get('form_value', '')}」 vs OCR:「{account_number_comp.get('ocr_value', '')}」)"
            )

        account_holder_comp = comparisons.get("account_holder", {})
        if account_holder_status == "verified":
            recommendations.append("✅ 戶名: 通過")
        elif account_holder_status == "needs_review":
            recommendations.append(
                f"⚠️ 戶名: 需人工檢閱 (表單:「{account_holder_comp.get('form_value', '')}」 vs OCR:「{account_holder_comp.get('ocr_value', '')}」)"
            )
        elif account_holder_status == "failed":
            recommendations.append(
                f"❌ 戶名: 不通過 (表單:「{account_holder_comp.get('form_value', '')}」 vs OCR:「{account_holder_comp.get('ocr_value', '')}」)"
            )

        if any(comp.get("confidence") == "low" for comp in comparisons.values()):
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

    async def manual_review_bank_info(
        self,
        application_id: int,
        account_number_approved: Optional[bool],
        account_number_corrected: Optional[str],
        account_holder_approved: Optional[bool],
        account_holder_corrected: Optional[str],
        review_notes: Optional[str],
        reviewer_username: str,
    ) -> Dict[str, Any]:
        """
        Process manual review of bank account information

        Args:
            application_id: Application ID to review
            account_number_approved: Whether account number is approved (True/False/None)
            account_number_corrected: Corrected account number if needed
            account_holder_approved: Whether account holder is approved (True/False/None)
            account_holder_corrected: Corrected account holder name if needed
            review_notes: Notes from manual review
            reviewer_username: Username of the reviewer

        Returns:
            Dict containing review results and updated information
        """
        from datetime import datetime, timezone

        try:
            # Get application
            stmt = select(Application).where(Application.id == application_id)
            result = await self.db.execute(stmt)
            application = result.scalar_one_or_none()

            if not application:
                raise ValueError(f"Application with ID {application_id} not found")

            # Extract current bank fields
            current_bank_fields = self.extract_bank_fields_from_application(application)

            # Use deep copy to avoid nested reference issues
            updated_form_data = (
                copy.deepcopy(application.submitted_form_data) if application.submitted_form_data else {"fields": {}}
            )

            # Ensure fields dict exists
            if "fields" not in updated_form_data:
                updated_form_data["fields"] = {}

            # Track what was updated
            account_number_updated = False
            account_holder_updated = False

            # Validate account number format if provided
            if account_number_corrected:
                is_valid, error_message = self.validate_postal_account_format(account_number_corrected)
                if not is_valid:
                    raise ValueError(f"帳號格式驗證失敗: {error_message}")

            # Update account number if corrected
            if account_number_corrected:
                # Try to find existing field
                for key in ["postal_account", "bank_account", "account_number"]:
                    if key in updated_form_data["fields"]:
                        updated_form_data["fields"][key]["value"] = account_number_corrected
                        account_number_updated = True
                        break

                # If no existing field found, create a new one
                if not account_number_updated:
                    updated_form_data["fields"]["postal_account"] = {
                        "field_id": "postal_account",
                        "field_type": "text",
                        "value": account_number_corrected,
                        "required": True,
                    }
                    account_number_updated = True

            # Update account holder if corrected
            if account_holder_corrected:
                # Try to find existing field
                for key in ["account_holder", "account_name"]:
                    if key in updated_form_data["fields"]:
                        updated_form_data["fields"][key]["value"] = account_holder_corrected
                        account_holder_updated = True
                        break

                # If no existing field found, create a new one
                if not account_holder_updated:
                    updated_form_data["fields"]["account_holder"] = {
                        "field_id": "account_holder",
                        "field_type": "text",
                        "value": account_holder_corrected,
                        "required": True,
                    }
                    account_holder_updated = True

            # Update application with manual review data
            application.submitted_form_data = updated_form_data

            # Determine final status for each field
            # Status logic:
            # - If corrected value provided: "verified" (admin fixed it)
            # - If approved=True: "verified"
            # - If approved=False: "failed" (admin rejected it)
            # - If approved=None (not touched): "not_reviewed"

            if account_number_corrected:
                account_number_status = "verified"  # Corrected by admin
            elif account_number_approved is True:
                account_number_status = "verified"  # Approved by admin
            elif account_number_approved is False:
                account_number_status = "failed"  # Explicitly rejected
            else:
                account_number_status = "not_reviewed"  # Not touched

            if account_holder_corrected:
                account_holder_status = "verified"  # Corrected by admin
            elif account_holder_approved is True:
                account_holder_status = "verified"  # Approved by admin
            elif account_holder_approved is False:
                account_holder_status = "failed"  # Explicitly rejected
            else:
                account_holder_status = "not_reviewed"  # Not touched

            # Determine overall status based on individual field statuses
            if account_number_status == "verified" and account_holder_status == "verified":
                overall_status = "verified"
            elif account_number_status == "failed" or account_holder_status == "failed":
                overall_status = "verification_failed"
            elif account_number_status == "not_reviewed" and account_holder_status == "not_reviewed":
                overall_status = "not_reviewed"
            else:
                overall_status = "needs_review"  # Partial verification

            # Update application meta_data with separate statuses
            application.meta_data = application.meta_data or {}
            application.meta_data["bank_verification"] = {
                "overall_status": overall_status,
                "account_number_status": account_number_status,
                "account_holder_status": account_holder_status,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "requires_manual_review": False,  # Manual review completed
                "reviewed_by": reviewer_username,
                "review_notes": review_notes,
            }

            # Query related payment roster items to update their status
            roster_items_stmt = select(PaymentRosterItem).where(PaymentRosterItem.application_id == application_id)
            roster_items_result = await self.db.execute(roster_items_stmt)
            roster_items = roster_items_result.scalars().all()

            # Prepare verification details for storage
            review_timestamp = datetime.now(timezone.utc)
            verification_details = {
                "manual_review": {
                    "timestamp": review_timestamp.isoformat(),
                    "reviewed_by": reviewer_username,
                    "account_number": {
                        "status": account_number_status,
                        "corrected_value": account_number_corrected,
                        "approved": account_number_approved,
                    },
                    "account_holder": {
                        "status": account_holder_status,
                        "corrected_value": account_holder_corrected,
                        "approved": account_holder_approved,
                    },
                    "notes": review_notes,
                },
                "last_updated": review_timestamp.isoformat(),
            }

            # Update all related roster items with the new verification status
            for roster_item in roster_items:
                roster_item.bank_account_number_status = account_number_status
                roster_item.bank_account_holder_status = account_holder_status
                roster_item.bank_verification_details = verification_details
                roster_item.bank_manual_review_notes = review_notes

            # Save verified bank account for future reference
            # Only save if both account number and holder are verified
            if account_number_status == "verified" and account_holder_status == "verified":
                final_account_number = account_number_corrected or current_bank_fields.get("account_number", "")
                final_account_holder = account_holder_corrected or current_bank_fields.get("account_holder", "")

                if final_account_number and final_account_holder:
                    # Get passbook cover document (CRITICAL: must save photo)
                    passbook_doc = await self.get_bank_passbook_document(application)
                    if not passbook_doc or not passbook_doc.object_name:
                        raise ValueError("無法儲存已驗證帳戶：缺少帳本封面照片")

                    # Get AI verification confidence if available from meta_data
                    ai_confidence = None
                    if application.meta_data and "bank_verification" in application.meta_data:
                        ai_confidence = application.meta_data["bank_verification"].get("average_confidence")

                    # Check if this account already exists for this user
                    existing_account_stmt = select(StudentBankAccount).where(
                        StudentBankAccount.user_id == application.user_id,
                        StudentBankAccount.account_number == final_account_number,
                    )
                    existing_account_result = await self.db.execute(existing_account_stmt)
                    existing_account = existing_account_result.scalar_one_or_none()

                    if existing_account:
                        # Update existing record
                        # Get reviewer user_id
                        from app.models.user import User

                        reviewer_stmt = select(User).where(User.nycu_id == reviewer_username)
                        reviewer_result = await self.db.execute(reviewer_stmt)
                        reviewer = reviewer_result.scalar_one_or_none()

                        existing_account.account_holder = final_account_holder
                        existing_account.passbook_cover_object_name = passbook_doc.object_name  # Save photo
                        existing_account.verification_status = "verified"
                        existing_account.verification_method = "manual_verified"
                        existing_account.ai_verification_confidence = ai_confidence
                        existing_account.verified_at = review_timestamp
                        existing_account.verified_by_user_id = reviewer.id if reviewer else None
                        existing_account.verification_source_application_id = application.id
                        existing_account.is_active = True
                        existing_account.verification_notes = review_notes
                    else:
                        # Create new verified account record
                        # First, deactivate any other active accounts for this user
                        deactivate_stmt = select(StudentBankAccount).where(
                            StudentBankAccount.user_id == application.user_id, StudentBankAccount.is_active == True
                        )
                        deactivate_result = await self.db.execute(deactivate_stmt)
                        active_accounts = deactivate_result.scalars().all()
                        for acc in active_accounts:
                            acc.is_active = False

                        # Get reviewer user_id
                        from app.models.user import User

                        reviewer_stmt = select(User).where(User.nycu_id == reviewer_username)
                        reviewer_result = await self.db.execute(reviewer_stmt)
                        reviewer = reviewer_result.scalar_one_or_none()

                        # Create new record
                        new_account = StudentBankAccount(
                            user_id=application.user_id,
                            account_number=final_account_number,
                            account_holder=final_account_holder,
                            passbook_cover_object_name=passbook_doc.object_name,  # Save photo (CRITICAL)
                            verification_status="verified",
                            verification_method="manual_verified",
                            ai_verification_confidence=ai_confidence,
                            verified_at=review_timestamp,
                            verified_by_user_id=reviewer.id if reviewer else None,
                            verification_source_application_id=application.id,
                            is_active=True,
                            verification_notes=review_notes,
                        )
                        self.db.add(new_account)

            # Prepare result
            final_account_number = account_number_corrected or current_bank_fields.get("account_number", "")
            final_account_holder = account_holder_corrected or current_bank_fields.get("account_holder", "")

            review_result = {
                "success": True,
                "application_id": application_id,
                "account_number_status": account_number_status,
                "account_holder_status": account_holder_status,
                "updated_form_data": {
                    "account_number": final_account_number,
                    "account_holder": final_account_holder,
                },
                "review_timestamp": review_timestamp.isoformat(),
                "reviewed_by": reviewer_username,
                "review_notes": review_notes,
                "roster_items_updated": len(roster_items),
            }

            # Commit all changes in a transaction
            await self.db.commit()
            await self.db.refresh(application)

            return review_result

        except Exception as e:
            # Rollback on any error
            await self.db.rollback()
            raise ValueError(f"Failed to process manual review: {str(e)}") from e
