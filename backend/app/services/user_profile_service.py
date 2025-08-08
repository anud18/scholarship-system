"""
User Profile Service for managing user profile data
"""

import os
import base64
import uuid
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
from PIL import Image
import io

from app.models.user import User
from app.models.user_profile import UserProfile, UserProfileHistory
from app.schemas.user_profile import (
    UserProfileCreate, UserProfileUpdate, UserProfileResponse,
    BankDocumentPhotoUpload, CompleteUserProfileResponse
)
from app.core.config import settings


class UserProfileService:
    """Service for managing user profiles"""
    
    # Configurable upload settings from config
    UPLOAD_BASE_DIR = settings.upload_dir
    BANK_DOCUMENTS_DIR = "bank_documents"
    MAX_FILE_SIZE = settings.max_file_size
    MAX_IMAGE_SIZE = (settings.max_document_image_width, settings.max_document_image_height)
    ALLOWED_MIME_TYPES = {
        'image/jpeg': ['jpg', 'jpeg'],
        'image/png': ['png'],
        'image/webp': ['webp']
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.upload_path = os.path.join(self.UPLOAD_BASE_DIR, self.BANK_DOCUMENTS_DIR)
        
    async def get_user_profile(self, user_id: int) -> Optional[UserProfile]:
        """Get user profile by user ID"""
        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_complete_user_profile(self, user: User) -> CompleteUserProfileResponse:
        """Get complete user profile including read-only data"""
        # Get user profile
        profile = await self.get_user_profile(user.id)
        
        # Get student info if user is a student
        student_info = None
        if user.is_student():
            try:
                from app.services.application_service import get_student_data_from_user
                student_info = await get_student_data_from_user(user)
            except Exception:
                student_info = None
        
        # Build user info from User model (read-only data)
        user_info = {
            "id": user.id,
            "nycu_id": user.nycu_id,
            "name": user.name,
            "email": user.email,
            "user_type": user.user_type.value if user.user_type else None,
            "status": user.status.value if user.status else None,
            "dept_code": user.dept_code,
            "dept_name": user.dept_name,
            "role": user.role.value,
            "comment": user.comment,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
        }
        
        # Build response
        profile_response = None
        if profile:
            profile_response = UserProfileResponse.model_validate(profile)
        
        return CompleteUserProfileResponse(
            user_info=user_info,
            profile=profile_response,
            student_info=student_info
        )
    
    async def create_user_profile(
        self, 
        user_id: int, 
        profile_data: UserProfileCreate,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> UserProfile:
        """Create new user profile"""
        # Check if profile already exists
        existing_profile = await self.get_user_profile(user_id)
        if existing_profile:
            raise ValueError("User profile already exists")
        
        # Create profile
        profile = UserProfile(
            user_id=user_id,
            **profile_data.model_dump(exclude_unset=True)
        )
        
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        
        # Log profile creation
        await self._log_profile_change(
            user_id=user_id,
            field_name="profile_created",
            old_value=None,
            new_value="Profile created",
            change_reason="Initial profile creation",
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        return profile
    
    async def update_user_profile(
        self, 
        user_id: int, 
        profile_data: UserProfileUpdate,
        change_reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> UserProfile:
        """Update user profile"""
        # Get existing profile or create new one
        profile = await self.get_user_profile(user_id)
        if not profile:
            # Create new profile if it doesn't exist
            create_data = UserProfileCreate(**profile_data.model_dump(exclude_unset=True))
            return await self.create_user_profile(
                user_id=user_id,
                profile_data=create_data,
                ip_address=ip_address,
                user_agent=user_agent
            )
        
        # Track changes for audit log with schema-based validation to prevent mass assignment
        # This automatically stays in sync with schema changes
        allowed_fields = set(profile_data.model_fields.keys())
        
        update_dict = profile_data.model_dump(exclude_unset=True)
        
        for field_name, new_value in update_dict.items():
            if field_name in allowed_fields and hasattr(profile, field_name):
                old_value = getattr(profile, field_name)
                
                # Only log if value actually changed
                if old_value != new_value:
                    await self._log_profile_change(
                        user_id=user_id,
                        field_name=field_name,
                        old_value=str(old_value) if old_value is not None else None,
                        new_value=str(new_value) if new_value is not None else None,
                        change_reason=change_reason,
                        ip_address=ip_address,
                        user_agent=user_agent
                    )
                
                setattr(profile, field_name, new_value)
        
        # Update timestamp
        profile.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(profile)
        
        return profile
    
    async def upload_bank_document(
        self, 
        user_id: int, 
        document_upload: BankDocumentPhotoUpload,
        upload_dir: str = None
    ) -> str:
        """Upload and process bank document photo"""
        try:
            # Use configured upload directory
            if upload_dir is None:
                upload_dir = self.upload_path
            
            # Create upload directory if it doesn't exist
            os.makedirs(upload_dir, exist_ok=True)
            
            # More accurate base64 size estimation
            # Base64 encoding adds ~33% overhead, so actual size = base64_size * 3/4
            # But we need to account for padding characters
            base64_data = document_upload.photo_data.rstrip('=')
            estimated_size = len(base64_data) * 3 // 4
            
            # Add safety margin for estimation errors
            if estimated_size > self.MAX_FILE_SIZE * 0.9:  # 90% of max to be safe
                raise ValueError(f"File too large (estimated). Maximum size is {self.MAX_FILE_SIZE / 1024 / 1024:.1f}MB")
            
            # Decode base64 image
            try:
                image_data = base64.b64decode(document_upload.photo_data)
            except Exception as e:
                raise ValueError(f"Invalid base64 data: {str(e)}")
            
            # Verify actual size after decoding (final check)
            if len(image_data) > self.MAX_FILE_SIZE:
                raise ValueError(f"File too large. Maximum size is {self.MAX_FILE_SIZE / 1024 / 1024:.1f}MB")
            
            # Validate MIME type (try python-magic if available, fallback to content inspection)
            try:
                import magic
                mime = magic.from_buffer(image_data, mime=True)
            except ImportError:
                # Fallback: detect from image data using PIL
                try:
                    temp_image = Image.open(io.BytesIO(image_data))
                    format_to_mime = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}
                    mime = format_to_mime.get(temp_image.format, 'application/octet-stream')
                except:
                    mime = 'application/octet-stream'
            
            if mime not in self.ALLOWED_MIME_TYPES:
                raise ValueError(f"Invalid file type: {mime}. Allowed types: {', '.join(self.ALLOWED_MIME_TYPES.keys())}")
            
            # Virus scanning hook (if enabled)
            if settings.enable_virus_scan:
                scan_result = await self._scan_for_virus(image_data, mime)
                if not scan_result['is_safe']:
                    raise ValueError(f"File failed security scan: {scan_result.get('reason', 'Unknown threat detected')}")
            
            # Validate image
            image = Image.open(io.BytesIO(image_data))
            
            # Verify image format matches claimed MIME type
            format_to_mime = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}
            if image.format in format_to_mime:
                expected_mime = format_to_mime[image.format]
                if mime != expected_mime and not (mime == 'image/jpeg' and expected_mime == 'image/jpeg'):
                    raise ValueError(f"File content does not match declared type")
            
            # Resize image if needed (using configurable size)
            if image.size[0] > self.MAX_IMAGE_SIZE[0] or image.size[1] > self.MAX_IMAGE_SIZE[1]:
                image.thumbnail(self.MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
            
            # Generate unique filename based on validated MIME type
            valid_extensions = self.ALLOWED_MIME_TYPES.get(mime, ['jpg'])
            file_extension = valid_extensions[0]
            
            unique_filename = f"{user_id}_bank_doc_{uuid.uuid4().hex}.{file_extension}"
            file_path = os.path.join(upload_dir, unique_filename)
            
            # Save image
            image.save(file_path, optimize=True, quality=90)
            
            # Update profile with new document URL
            profile = await self.get_user_profile(user_id)
            if not profile:
                # Create profile if it doesn't exist
                profile = UserProfile(user_id=user_id)
                self.db.add(profile)
            
            # Store relative path for URL generation
            old_document_url = profile.bank_document_photo_url
            profile.bank_document_photo_url = f"/api/v1/user-profiles/files/bank_documents/{unique_filename}"
            profile.updated_at = datetime.now(timezone.utc)
            
            await self.db.commit()
            
            # Remove old document if it exists
            if old_document_url and old_document_url.startswith("/api/v1/user-profiles/files/bank_documents/"):
                old_filename = old_document_url.split('/')[-1]
                old_file_path = os.path.join(upload_dir, old_filename)
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
            
            # Log document upload
            await self._log_profile_change(
                user_id=user_id,
                field_name="bank_document_photo_url",
                old_value=old_document_url,
                new_value=profile.bank_document_photo_url,
                change_reason="Bank document uploaded"
            )
            
            return profile.bank_document_photo_url
            
        except Exception as e:
            raise ValueError(f"Failed to upload bank document: {str(e)}")
    
    async def delete_bank_document(self, user_id: int) -> bool:
        """Delete bank document"""
        profile = await self.get_user_profile(user_id)
        if not profile or not profile.bank_document_photo_url:
            return False
        
        # Delete file if it exists
        if profile.bank_document_photo_url.startswith("/api/v1/user-profiles/files/bank_documents/"):
            filename = profile.bank_document_photo_url.split('/')[-1]
            file_path = os.path.join(self.upload_path, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Update profile
        old_document_url = profile.bank_document_photo_url
        profile.bank_document_photo_url = None
        profile.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        
        # Log document deletion
        await self._log_profile_change(
            user_id=user_id,
            field_name="bank_document_photo_url",
            old_value=old_document_url,
            new_value=None,
            change_reason="Bank document deleted"
        )
        
        return True
    
    async def _scan_for_virus(self, file_data: bytes, mime_type: str) -> dict:
        """
        Virus scanning hook for uploaded files.
        
        This is a placeholder implementation that can be replaced with actual
        virus scanning service integration (e.g., ClamAV, VirusTotal, etc.)
        
        Args:
            file_data: File content as bytes
            mime_type: MIME type of the file
            
        Returns:
            dict with 'is_safe' (bool) and optional 'reason' (str) if not safe
        """
        # Placeholder implementation
        # In production, integrate with actual virus scanning service
        
        if not settings.virus_scan_api_url or not settings.virus_scan_api_key:
            # If not configured, log warning but allow upload
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Virus scanning enabled but not configured properly")
            return {'is_safe': True, 'warning': 'Scanner not configured'}
        
        try:
            # Example integration point for virus scanning service
            # This would be replaced with actual API call to virus scanner
            import aiohttp
            import asyncio
            
            async with aiohttp.ClientSession() as session:
                headers = {
                    'X-API-Key': settings.virus_scan_api_key,
                    'Content-Type': 'application/octet-stream'
                }
                
                timeout = aiohttp.ClientTimeout(total=settings.virus_scan_timeout)
                
                async with session.post(
                    settings.virus_scan_api_url,
                    data=file_data,
                    headers=headers,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return {
                            'is_safe': result.get('clean', True),
                            'reason': result.get('malware_name', None)
                        }
                    else:
                        # Scanner error, log but don't block upload
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Virus scanner returned status {response.status}")
                        return {'is_safe': True, 'warning': 'Scanner error'}
                        
        except Exception as e:
            # Don't block uploads on scanner errors
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Virus scanning failed: {str(e)}")
            return {'is_safe': True, 'warning': f'Scanner exception: {str(e)}'}
    
    async def get_profile_history(
        self, 
        user_id: int, 
        limit: int = 50
    ) -> List[UserProfileHistory]:
        """Get profile change history"""
        stmt = (
            select(UserProfileHistory)
            .where(UserProfileHistory.user_id == user_id)
            .order_by(UserProfileHistory.changed_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def delete_user_profile(self, user_id: int) -> bool:
        """Delete user profile and associated data"""
        # Delete bank document if it exists
        await self.delete_bank_document(user_id)
        
        # Delete profile history
        await self.db.execute(
            delete(UserProfileHistory).where(UserProfileHistory.user_id == user_id)
        )
        
        # Delete profile
        result = await self.db.execute(
            delete(UserProfile).where(UserProfile.user_id == user_id)
        )
        
        await self.db.commit()
        
        return result.rowcount > 0
    
    async def _log_profile_change(
        self,
        user_id: int,
        field_name: str,
        old_value: Optional[str],
        new_value: Optional[str],
        change_reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Log profile changes for audit purposes"""
        history_entry = UserProfileHistory(
            user_id=user_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            change_reason=change_reason,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.db.add(history_entry)
        # Note: commit is handled by the calling method
    
    async def get_users_with_incomplete_profiles(self) -> List[Dict[str, Any]]:
        """Get users with incomplete profiles for admin dashboard"""
        stmt = (
            select(User, UserProfile)
            .outerjoin(UserProfile)
            .where(User.role == 'STUDENT')
        )
        
        result = await self.db.execute(stmt)
        users_profiles = result.all()
        
        incomplete_users = []
        for user, profile in users_profiles:
            if not profile:
                completion_percentage = 0
                missing_info = ["所有個人資料"]
            else:
                completion_percentage = profile.profile_completion_percentage
                missing_info = []
                
                if not profile.has_complete_bank_info:
                    missing_info.append("銀行帳戶資訊")
                if not profile.has_advisor_info:
                    missing_info.append("指導教授資訊")
                if not profile.preferred_email:
                    missing_info.append("聯絡Email")
                if not profile.phone_number:
                    missing_info.append("聯絡電話")
            
            if completion_percentage < 80:  # Consider <80% as incomplete
                incomplete_users.append({
                    "user_id": user.id,
                    "name": user.name,
                    "nycu_id": user.nycu_id,
                    "email": user.email,
                    "completion_percentage": completion_percentage,
                    "missing_info": missing_info,
                    "last_login_at": user.last_login_at
                })
        
        return incomplete_users
    
    async def bulk_update_privacy_settings(
        self,
        user_id: int,
        privacy_settings: Dict[str, Any]
    ) -> UserProfile:
        """Update privacy settings for user profile"""
        profile = await self.get_user_profile(user_id)
        if not profile:
            # Create profile if it doesn't exist
            profile = UserProfile(user_id=user_id, privacy_settings=privacy_settings)
            self.db.add(profile)
        else:
            profile.privacy_settings = privacy_settings
            profile.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(profile)
        
        # Log privacy settings update
        await self._log_profile_change(
            user_id=user_id,
            field_name="privacy_settings",
            old_value=None,  # Don't log sensitive privacy settings values
            new_value="Privacy settings updated",
            change_reason="Privacy settings bulk update"
        )
        
        return profile