"""
Application field configuration service
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.models.application_field import ApplicationField, ApplicationDocument
from app.schemas.application_field import (
    ApplicationFieldCreate, ApplicationFieldUpdate, ApplicationFieldResponse,
    ApplicationDocumentCreate, ApplicationDocumentUpdate, ApplicationDocumentResponse,
    ScholarshipFormConfigResponse
)


class ApplicationFieldService:
    """Service for managing application field configurations"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # Application Field methods
    async def get_fields_by_scholarship_type(self, scholarship_type: str, include_inactive: bool = False) -> List[ApplicationFieldResponse]:
        """Get fields for a scholarship type"""
        query = select(ApplicationField).where(
            ApplicationField.scholarship_type == scholarship_type
        )
        
        # 如果不需要包含停用的欄位，則只返回啟用的
        if not include_inactive:
            query = query.where(ApplicationField.is_active == True)
        
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
        field = ApplicationField(
            **field_data.model_dump(),
            created_by=created_by,
            updated_by=created_by
        )
        
        self.db.add(field)
        await self.db.commit()
        await self.db.refresh(field)
        
        return ApplicationFieldResponse.model_validate(field)
    
    async def update_field(self, field_id: int, field_data: ApplicationFieldUpdate, updated_by: int) -> Optional[ApplicationFieldResponse]:
        """Update an application field"""
        query = select(ApplicationField).where(ApplicationField.id == field_id)
        result = await self.db.execute(query)
        field = result.scalar_one_or_none()
        
        if not field:
            return None
        
        # Update only provided fields
        update_data = field_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
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
    
    async def bulk_update_fields(self, scholarship_type: str, fields_data: List[Dict[str, Any]], updated_by: int) -> List[ApplicationFieldResponse]:
        """Bulk update fields for a scholarship type"""
        # First, delete existing fields for this scholarship type
        await self.db.execute(
            delete(ApplicationField).where(ApplicationField.scholarship_type == scholarship_type)
        )
        
        # Create new fields
        created_fields = []
        for field_data in fields_data:
            field = ApplicationField(
                scholarship_type=scholarship_type,
                **field_data,
                created_by=updated_by,
                updated_by=updated_by
            )
            self.db.add(field)
            created_fields.append(field)
        
        await self.db.commit()
        
        # Refresh all fields
        for field in created_fields:
            await self.db.refresh(field)
        
        return [ApplicationFieldResponse.model_validate(field) for field in created_fields]
    
    # Application Document methods
    async def get_documents_by_scholarship_type(self, scholarship_type: str, include_inactive: bool = False) -> List[ApplicationDocumentResponse]:
        """Get documents for a scholarship type"""
        query = select(ApplicationDocument).where(
            ApplicationDocument.scholarship_type == scholarship_type
        )
        
        # 如果不需要包含停用的文件，則只返回啟用的
        if not include_inactive:
            query = query.where(ApplicationDocument.is_active == True)
        
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
    
    async def create_document(self, document_data: ApplicationDocumentCreate, created_by: int) -> ApplicationDocumentResponse:
        """Create a new application document"""
        document = ApplicationDocument(
            **document_data.model_dump(),
            created_by=created_by,
            updated_by=created_by
        )
        
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        
        return ApplicationDocumentResponse.model_validate(document)
    
    async def update_document(self, document_id: int, document_data: ApplicationDocumentUpdate, updated_by: int) -> Optional[ApplicationDocumentResponse]:
        """Update an application document"""
        query = select(ApplicationDocument).where(ApplicationDocument.id == document_id)
        result = await self.db.execute(query)
        document = result.scalar_one_or_none()
        
        if not document:
            return None
        
        # Update only provided fields
        update_data = document_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
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
    
    async def bulk_update_documents(self, scholarship_type: str, documents_data: List[Dict[str, Any]], updated_by: int) -> List[ApplicationDocumentResponse]:
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
                updated_by=updated_by
            )
            self.db.add(document)
            created_documents.append(document)
        
        await self.db.commit()
        
        # Refresh all documents
        for document in created_documents:
            await self.db.refresh(document)
        
        return [ApplicationDocumentResponse.model_validate(doc) for doc in created_documents]
    
    # Combined methods
    async def get_scholarship_form_config(self, scholarship_type: str, include_inactive: bool = False) -> ScholarshipFormConfigResponse:
        """Get complete form configuration for a scholarship type"""
        try:
            print(f"🔍 Fetching form config for scholarship type: {scholarship_type}")
            
            fields = await self.get_fields_by_scholarship_type(scholarship_type, include_inactive)
            print(f"📝 Found {len(fields)} fields for {scholarship_type}")
            
            documents = await self.get_documents_by_scholarship_type(scholarship_type, include_inactive)
            print(f"📄 Found {len(documents)} documents for {scholarship_type}")
            
            config = ScholarshipFormConfigResponse(
                scholarship_type=scholarship_type,
                fields=fields,
                documents=documents
            )
            
            print(f"✅ Form config created successfully for {scholarship_type}")
            return config
            
        except Exception as e:
            print(f"❌ Error getting form config for {scholarship_type}: {str(e)}")
            # Re-raise the exception instead of returning empty config
            raise e
    
    async def save_scholarship_form_config(
        self, 
        scholarship_type: str, 
        fields_data: List[Dict[str, Any]], 
        documents_data: List[Dict[str, Any]], 
        user_id: int
    ) -> ScholarshipFormConfigResponse:
        """Save complete form configuration for a scholarship type"""
        
        # Update fields and documents
        fields = await self.bulk_update_fields(scholarship_type, fields_data, user_id)
        documents = await self.bulk_update_documents(scholarship_type, documents_data, user_id)
        
        return ScholarshipFormConfigResponse(
            scholarship_type=scholarship_type,
            fields=fields,
            documents=documents
        ) 