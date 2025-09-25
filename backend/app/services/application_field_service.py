"""
Application field configuration service
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_field import ApplicationDocument, ApplicationField
from app.models.scholarship import ScholarshipConfiguration
from app.models.user_profile import UserProfile
from app.schemas.application_field import (
    ApplicationDocumentCreate,
    ApplicationDocumentResponse,
    ApplicationDocumentUpdate,
    ApplicationFieldCreate,
    ApplicationFieldResponse,
    ApplicationFieldUpdate,
    ScholarshipFormConfigResponse,
)


class ApplicationFieldService:
    """Service for managing application field configurations"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.logger = logging.getLogger(__name__)

    # Application Field methods
    async def get_fields_by_scholarship_type(
        self, scholarship_type: str, include_inactive: bool = False
    ) -> List[ApplicationFieldResponse]:
        """Get fields for a scholarship type"""
        query = select(ApplicationField).where(ApplicationField.scholarship_type == scholarship_type)

        # 如果不需要包含停用的欄位，則只返回啟用的
        if not include_inactive:
            query = query.where(ApplicationField.is_active.is_(True))

        query = query.order_by(ApplicationField.display_order, ApplicationField.id)

        result = await self.db.execute(query)
        fields = result.scalars().all()

        return [ApplicationFieldResponse.model_validate(field) for field in fields]

    async def get_field_by_id(self, field_id: int) -> Optional[ApplicationFieldResponse]:
        """Get field by ID"""
        query = select(ApplicationField).where(ApplicationField.id == field_id)
        result = await self.db.execute(query)
        field = result.scalar_one_or_none()

        if field:
            return ApplicationFieldResponse.model_validate(field)
        return None

    async def create_field(self, field_data: ApplicationFieldCreate, created_by: int) -> ApplicationFieldResponse:
        """Create a new application field"""
        field = ApplicationField(**field_data.model_dump(), created_by=created_by, updated_by=created_by)

        self.db.add(field)
        await self.db.commit()
        await self.db.refresh(field)

        return ApplicationFieldResponse.model_validate(field)

    async def update_field(
        self, field_id: int, field_data: ApplicationFieldUpdate, updated_by: int
    ) -> Optional[ApplicationFieldResponse]:
        """Update an application field"""
        query = select(ApplicationField).where(ApplicationField.id == field_id)
        result = await self.db.execute(query)
        field = result.scalar_one_or_none()

        if not field:
            return None

        # Update only fields defined in the Pydantic schema to prevent mass assignment
        # This automatically stays in sync with schema changes
        allowed_fields = set(field_data.model_fields.keys())

        update_data = field_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key in allowed_fields and hasattr(field, key):
                setattr(field, key, value)

        field.updated_by = updated_by

        await self.db.commit()
        await self.db.refresh(field)

        return ApplicationFieldResponse.model_validate(field)

    async def delete_field(self, field_id: int) -> bool:
        """Delete an application field"""
        query = delete(ApplicationField).where(ApplicationField.id == field_id)
        result = await self.db.execute(query)
        await self.db.commit()

        return result.rowcount > 0

    async def bulk_update_fields(
        self, scholarship_type: str, fields_data: List[Dict[str, Any]], updated_by: int
    ) -> List[ApplicationFieldResponse]:
        """Bulk update fields for a scholarship type"""
        # First, delete existing fields for this scholarship type
        await self.db.execute(delete(ApplicationField).where(ApplicationField.scholarship_type == scholarship_type))

        # Create new fields
        created_fields = []
        for field_data in fields_data:
            field = ApplicationField(
                scholarship_type=scholarship_type,
                **field_data,
                created_by=updated_by,
                updated_by=updated_by,
            )
            self.db.add(field)
            created_fields.append(field)

        await self.db.commit()

        # Refresh all fields
        for field in created_fields:
            await self.db.refresh(field)

        return [ApplicationFieldResponse.model_validate(field) for field in created_fields]

    # Application Document methods
    async def get_documents_by_scholarship_type(
        self, scholarship_type: str, include_inactive: bool = False
    ) -> List[ApplicationDocumentResponse]:
        """Get documents for a scholarship type"""
        query = select(ApplicationDocument).where(ApplicationDocument.scholarship_type == scholarship_type)

        # 如果不需要包含停用的文件，則只返回啟用的
        if not include_inactive:
            query = query.where(ApplicationDocument.is_active.is_(True))

        query = query.order_by(ApplicationDocument.display_order, ApplicationDocument.id)

        result = await self.db.execute(query)
        documents = result.scalars().all()

        return [ApplicationDocumentResponse.model_validate(doc) for doc in documents]

    async def get_document_by_id(self, document_id: int) -> Optional[ApplicationDocumentResponse]:
        """Get document by ID"""
        query = select(ApplicationDocument).where(ApplicationDocument.id == document_id)
        result = await self.db.execute(query)
        document = result.scalar_one_or_none()

        if document:
            return ApplicationDocumentResponse.model_validate(document)
        return None

    async def create_document(
        self, document_data: ApplicationDocumentCreate, created_by: int
    ) -> ApplicationDocumentResponse:
        """Create a new application document"""
        document = ApplicationDocument(**document_data.model_dump(), created_by=created_by, updated_by=created_by)

        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)

        return ApplicationDocumentResponse.model_validate(document)

    async def update_document(
        self,
        document_id: int,
        document_data: ApplicationDocumentUpdate,
        updated_by: int,
    ) -> Optional[ApplicationDocumentResponse]:
        """Update an application document"""
        query = select(ApplicationDocument).where(ApplicationDocument.id == document_id)
        result = await self.db.execute(query)
        document = result.scalar_one_or_none()

        if not document:
            return None

        # Update only fields defined in the Pydantic schema to prevent mass assignment
        # This automatically stays in sync with schema changes
        allowed_fields = set(document_data.model_fields.keys())

        update_data = document_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key in allowed_fields and hasattr(document, key):
                setattr(document, key, value)

        document.updated_by = updated_by

        await self.db.commit()
        await self.db.refresh(document)

        return ApplicationDocumentResponse.model_validate(document)

    async def delete_document(self, document_id: int) -> bool:
        """Delete an application document"""
        query = delete(ApplicationDocument).where(ApplicationDocument.id == document_id)
        result = await self.db.execute(query)
        await self.db.commit()

        return result.rowcount > 0

    async def bulk_update_documents(
        self,
        scholarship_type: str,
        documents_data: List[Dict[str, Any]],
        updated_by: int,
    ) -> List[ApplicationDocumentResponse]:
        """Bulk update documents for a scholarship type"""
        # First, delete existing documents for this scholarship type
        await self.db.execute(
            delete(ApplicationDocument).where(ApplicationDocument.scholarship_type == scholarship_type)
        )

        # Create new documents
        created_documents = []
        for doc_data in documents_data:
            document = ApplicationDocument(
                scholarship_type=scholarship_type,
                **doc_data,
                created_by=updated_by,
                updated_by=updated_by,
            )
            self.db.add(document)
            created_documents.append(document)

        await self.db.commit()

        # Refresh all documents
        for document in created_documents:
            await self.db.refresh(document)

        return [ApplicationDocumentResponse.model_validate(doc) for doc in created_documents]

    # Fixed fields methods
    async def get_user_profile_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user profile data for auto-filling fixed fields"""
        try:
            query = select(UserProfile).where(UserProfile.user_id == user_id)
            result = await self.db.execute(query)
            profile = result.scalar_one_or_none()

            if profile:
                return {
                    "bank_code": profile.bank_code,
                    "account_number": profile.account_number,
                    "bank_document_photo_url": profile.bank_document_photo_url,
                    "advisor_name": profile.advisor_name,
                    "advisor_email": profile.advisor_email,
                    "advisor_nycu_id": profile.advisor_nycu_id,
                }
            return None
        except Exception as e:
            self.logger.error(f"Error fetching user profile data: {str(e)}")
            return None

    def _create_fixed_bank_account_field(
        self,
        display_order: int = 1,
        prefill_data: Dict[str, Any] = None,
        scholarship_type: str = "fixed",
    ) -> Dict[str, Any]:
        """Create fixed bank account field definition"""
        from datetime import datetime

        return {
            "id": 0,  # Temporary ID for fixed field
            "scholarship_type": scholarship_type,
            "field_name": "bank_account",
            "field_label": "郵局局帳號/玉山帳號",
            "field_label_en": "Post Office/ESUN Bank Account Number",
            "field_type": "text",
            "is_required": True,
            "is_fixed": True,  # Mark as fixed field
            "placeholder": "請輸入您的郵局局帳號或玉山銀行帳號",
            "placeholder_en": "Please enter your Post Office or ESUN Bank account number",
            "max_length": 30,
            "display_order": display_order,
            "is_active": True,
            "help_text": "請填寫正確的郵局局帳號或玉山銀行帳號以便獎學金匯款",
            "help_text_en": "Please provide your correct Post Office or ESUN Bank account number for scholarship remittance",
            "prefill_value": prefill_data.get("account_number", "") if prefill_data else "",
            "bank_code": prefill_data.get("bank_code", "") if prefill_data else "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": 0,
            "updated_by": 0,
        }

    def _create_fixed_bank_statement_document(
        self,
        display_order: int = 1,
        prefill_data: Dict[str, Any] = None,
        scholarship_type: str = "fixed",
    ) -> Dict[str, Any]:
        """Create fixed bank statement cover document definition"""
        from datetime import datetime

        return {
            "id": 0,  # Temporary ID for fixed document
            "scholarship_type": scholarship_type,
            "document_name": "存摺封面",
            "document_name_en": "Bank Statement Cover",
            "description": "請上傳存摺封面",
            "description_en": "Please upload bank statement cover",
            "is_required": True,
            "is_fixed": True,  # Mark as fixed document
            "accepted_file_types": ["PDF", "JPG", "PNG"],
            "max_file_size": "10MB",
            "max_file_count": 1,
            "display_order": display_order,
            "is_active": True,
            "upload_instructions": "請確保存摺封面清晰可讀，包含戶名、帳號、銀行名稱等資訊",
            "upload_instructions_en": "Please ensure the bank statement cover is clear and readable, including account name, account number, bank name, etc.",
            "existing_file_url": prefill_data.get("bank_document_photo_url", "") if prefill_data else "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": 0,
            "updated_by": 0,
        }

    def _create_fixed_advisor_fields(
        self,
        display_order_start: int = 1,
        prefill_data: Dict[str, Any] = None,
        scholarship_type: str = "fixed",
    ) -> List[Dict[str, Any]]:
        """Create fixed advisor information fields"""
        from datetime import datetime

        fields = []

        # Advisor name field
        fields.append(
            {
                "id": 0,  # Temporary ID for fixed field
                "scholarship_type": scholarship_type,
                "field_name": "advisor_name",
                "field_label": "指導教授姓名",
                "field_label_en": "Advisor Name",
                "field_type": "text",
                "is_required": True,
                "is_fixed": True,  # Mark as fixed field
                "placeholder": "請輸入指導教授的姓名",
                "placeholder_en": "Please enter the name of the advisor",
                "max_length": 100,
                "display_order": display_order_start,
                "is_active": True,
                "help_text": "請填寫指導教授的姓名",
                "help_text_en": "Please provide the name of the advisor",
                "prefill_value": prefill_data.get("advisor_name", "") if prefill_data else "",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "created_by": 0,
                "updated_by": 0,
            }
        )

        # Advisor email field
        fields.append(
            {
                "id": 0,  # Temporary ID for fixed field
                "scholarship_type": scholarship_type,
                "field_name": "advisor_email",
                "field_label": "指導教授Email",
                "field_label_en": "Advisor Email",
                "field_type": "email",
                "is_required": True,
                "is_fixed": True,  # Mark as fixed field
                "placeholder": "請輸入指導教授的Email",
                "placeholder_en": "Please enter the email of the advisor",
                "max_length": 100,
                "display_order": display_order_start + 1,
                "is_active": True,
                "help_text": "請填寫指導教授的Email",
                "help_text_en": "Please provide the email of the advisor",
                "prefill_value": prefill_data.get("advisor_email", "") if prefill_data else "",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "created_by": 0,
                "updated_by": 0,
            }
        )

        # Advisor NYCU ID field
        fields.append(
            {
                "id": 0,  # Temporary ID for fixed field
                "scholarship_type": scholarship_type,
                "field_name": "advisor_nycu_id",
                "field_label": "指導教授交大編號",
                "field_label_en": "Advisor NYCU ID",
                "field_type": "text",
                "is_required": True,
                "is_fixed": True,  # Mark as fixed field
                "placeholder": "請輸入指導教授的交大編號",
                "placeholder_en": "Please enter the advisor NYCU ID",
                "max_length": 20,
                "display_order": display_order_start + 2,
                "is_active": True,
                "help_text": "請填寫指導教授的交大編號（必填）",
                "help_text_en": "Please provide the advisor NYCU ID (required)",
                "prefill_value": prefill_data.get("advisor_nycu_id", "") if prefill_data else "",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "created_by": 0,
                "updated_by": 0,
            }
        )

        return fields

    async def check_requires_professor_recommendation(self, scholarship_type: str) -> bool:
        """Check if scholarship configuration requires professor recommendation"""
        try:
            # Query scholarship configurations to check requires_professor_recommendation
            query = select(ScholarshipConfiguration).where(
                ScholarshipConfiguration.scholarship_type_id.in_(
                    select(ScholarshipConfiguration.scholarship_type_id).where(
                        ScholarshipConfiguration.is_active.is_(True)
                    )
                )
            )
            result = await self.db.execute(query)
            configs = result.scalars().all()

            for config in configs:
                if config.requires_professor_recommendation:
                    return True

            return False
        except Exception as e:
            self.logger.error(f"Error checking professor recommendation requirement: {str(e)}")
            return False

    async def inject_fixed_fields(
        self,
        scholarship_type: str,
        fields: List[Dict[str, Any]],
        documents: List[Dict[str, Any]],
        user_id: Optional[int] = None,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Inject fixed fields and documents into the form configuration"""
        try:
            # Get user profile data if user_id is provided
            profile_data = None
            if user_id:
                profile_data = await self.get_user_profile_data(user_id)

            # Calculate display orders
            max_field_order = max([f.get("display_order", 0) for f in fields], default=0)
            max_doc_order = max([d.get("display_order", 0) for d in documents], default=0)

            # Always inject bank account field and bank statement document
            bank_field = self._create_fixed_bank_account_field(
                display_order=max_field_order + 1,
                prefill_data=profile_data,
                scholarship_type=scholarship_type,
            )
            fields.append(bank_field)

            bank_doc = self._create_fixed_bank_statement_document(
                display_order=max_doc_order + 1,
                prefill_data=profile_data,
                scholarship_type=scholarship_type,
            )
            documents.append(bank_doc)

            # Inject advisor fields if required
            requires_advisor = await self.check_requires_professor_recommendation(scholarship_type)
            if requires_advisor:
                advisor_fields = self._create_fixed_advisor_fields(
                    display_order_start=max_field_order + 2,
                    prefill_data=profile_data,
                    scholarship_type=scholarship_type,
                )
                fields.extend(advisor_fields)

            self.logger.info(
                f"Injected fixed fields for {scholarship_type}: bank_account, bank_statement"
                + (", advisor_info" if requires_advisor else "")
            )

            return fields, documents

        except Exception as e:
            self.logger.error(f"Error injecting fixed fields: {str(e)}")
            return fields, documents

    # Combined methods
    async def get_scholarship_form_config(
        self,
        scholarship_type: str,
        include_inactive: bool = False,
        user_id: Optional[int] = None,
    ) -> ScholarshipFormConfigResponse:
        """Get complete form configuration for a scholarship type with fixed fields injection"""
        try:
            self.logger.debug(f"Fetching form config for scholarship type: {scholarship_type}")

            fields = await self.get_fields_by_scholarship_type(scholarship_type, include_inactive)
            self.logger.debug(f"Found {len(fields)} fields for {scholarship_type}")

            documents = await self.get_documents_by_scholarship_type(scholarship_type, include_inactive)
            self.logger.debug(f"Found {len(documents)} documents for {scholarship_type}")

            # Convert to dict format for fixed fields injection
            fields_dict = [field.model_dump() if hasattr(field, "model_dump") else field for field in fields]
            documents_dict = [doc.model_dump() if hasattr(doc, "model_dump") else doc for doc in documents]

            # Inject fixed fields and documents
            fields_dict, documents_dict = await self.inject_fixed_fields(
                scholarship_type=scholarship_type,
                fields=fields_dict,
                documents=documents_dict,
                user_id=user_id,
            )

            self.logger.debug(
                f"Fixed fields injected, total fields: {len(fields_dict)}, total documents: {len(documents_dict)}"
            )

            # Create config using model_validate to handle extra fields
            config_data = {
                "scholarship_type": scholarship_type,
                "fields": fields_dict,
                "documents": documents_dict,
            }
            config = ScholarshipFormConfigResponse.model_validate(config_data)

            self.logger.info(f"Form config created successfully for {scholarship_type}")
            return config

        except Exception as e:
            self.logger.error(f"Error getting form config for {scholarship_type}: {str(e)}")
            # Re-raise the exception instead of returning empty config
            raise e

    async def save_scholarship_form_config(
        self,
        scholarship_type: str,
        fields_data: List[Dict[str, Any]],
        documents_data: List[Dict[str, Any]],
        user_id: int,
    ) -> ScholarshipFormConfigResponse:
        """Save complete form configuration for a scholarship type"""

        # Update fields and documents
        fields = await self.bulk_update_fields(scholarship_type, fields_data, user_id)
        documents = await self.bulk_update_documents(scholarship_type, documents_data, user_id)

        return ScholarshipFormConfigResponse(scholarship_type=scholarship_type, fields=fields, documents=documents)
