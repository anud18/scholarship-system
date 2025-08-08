"""
MinIO file storage service
"""

import io
import uuid
import hashlib
import time
import logging
from datetime import timedelta
from typing import Optional, Tuple
from minio import Minio
from minio.error import S3Error
from fastapi import UploadFile, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

class MinIOService:
    def __init__(self):
        self.client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        self.bucket_name = settings.minio_bucket
        
        # Skip bucket check during testing to avoid connection issues
        if not getattr(settings, 'testing', False):
            self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Ensure the bucket exists, create if it doesn't"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"Error ensuring bucket exists: {e}")
            raise HTTPException(status_code=500, detail="Storage service unavailable")
    
    async def upload_file(
        self, 
        file: UploadFile, 
        application_id: int, 
        file_type: str
    ) -> Tuple[str, int]:
        """
        Upload file to MinIO
        
        Args:
            file: The uploaded file
            application_id: The application ID
            file_type: The type of document
            
        Returns:
            Tuple of (object_name, file_size)
        """
        try:
            # Validate file size
            file_content = await file.read()
            file_size = len(file_content)
            
            if file_size > settings.max_file_size:
                raise HTTPException(
                    status_code=413, 
                    detail=f"File size exceeds limit of {settings.max_file_size} bytes"
                )
            
            # Validate file type
            file_extension = file.filename.split('.')[-1].lower() if file.filename else ''
            if file_extension not in settings.allowed_file_types_list:
                raise HTTPException(
                    status_code=400,
                    detail=f"File type '{file_extension}' not allowed. Allowed types: {', '.join(settings.allowed_file_types_list)}"
                )
            
            # Generate unique object name using timestamp + hash + UUID for maximum uniqueness
            timestamp = int(time.time() * 1000000)  # Microsecond precision
            file_content_hash = hashlib.sha256(file_content).hexdigest()[:16]  # First 16 chars of hash
            unique_id = str(uuid.uuid4())[:8]  # First 8 chars of UUID
            file_extension = file.filename.split('.')[-1].lower() if file.filename else ''
            
            # Format: timestamp_hash_uuid.extension
            object_name = f"applications/{application_id}/{file_type}/{timestamp}_{file_content_hash}_{unique_id}.{file_extension}"
            
            # Upload to MinIO
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=io.BytesIO(file_content),
                length=file_size,
                content_type=file.content_type or 'application/octet-stream'
            )
            
            logger.info(f"Successfully uploaded file: {object_name}")
            return object_name, file_size
            
        except S3Error as e:
            logger.error(f"MinIO upload error: {e}")
            raise HTTPException(status_code=500, detail="File upload failed")
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
    
    def get_file_stream(self, object_name: str):
        """
        Get file stream directly from MinIO (for backend proxy)
        
        Args:
            object_name: The object name in MinIO
            
        Returns:
            File stream and metadata
        """
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            return response
        except S3Error as e:
            logger.error(f"Error getting file stream for {object_name}: {e}")
            raise HTTPException(status_code=404, detail="File not found")
    
    def delete_file(self, object_name: str) -> bool:
        """
        Delete file from MinIO
        
        Args:
            object_name: The object name to delete
            
        Returns:
            True if successful
        """
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info(f"Successfully deleted file: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Error deleting file: {e}")
            return False

# Global instance
minio_service = MinIOService() 