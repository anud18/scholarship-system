"""
Portal SSO service for NYCU Portal integration
Handles real JWT token verification with Portal JWT server
"""

import httpx
import json
import logging
from typing import Dict, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.models.user import User, UserRole, UserType, EmployeeStatus
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class PortalSSOService:
    """Portal SSO service for NYCU Portal integration"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.auth_service = AuthService(db)
    
    async def verify_portal_token(self, token: str) -> Dict:
        """
        Verify token with Portal JWT server and return user data
        
        Args:
            token: JWT token received from Portal
            
        Returns:
            Dict containing user data from Portal
            
        Raises:
            AuthenticationError: If token verification fails
        """
        if not settings.portal_sso_enabled:
            raise AuthenticationError("Portal SSO is disabled")
        
        if settings.portal_test_mode:
            return self._get_test_portal_data()
        
        try:
            async with httpx.AsyncClient(timeout=settings.portal_sso_timeout) as client:
                # Post token to Portal JWT server for verification
                response = await client.post(
                    settings.portal_jwt_server_url,
                    json={"token": token},
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code != 200:
                    logger.error(f"Portal JWT verification failed: {response.status_code} - {response.text}")
                    raise AuthenticationError(f"Portal token verification failed: {response.status_code}")
                
                portal_data = response.json()
                
                # Validate portal response format
                if not self._validate_portal_response(portal_data):
                    logger.error(f"Invalid portal response format: {portal_data}")
                    raise AuthenticationError("Invalid portal response format")
                
                return portal_data
                
        except httpx.TimeoutException:
            logger.error("Portal JWT verification timeout")
            raise AuthenticationError("Portal verification timeout")
        except httpx.RequestError as e:
            logger.error(f"Portal JWT verification request error: {e}")
            raise AuthenticationError("Portal verification failed")
        except json.JSONDecodeError:
            logger.error("Portal JWT verification returned invalid JSON")
            raise AuthenticationError("Invalid portal response")
    
    def _validate_portal_response(self, data: Dict) -> bool:
        """Validate portal response contains required fields"""
        required_fields = ["txtID", "nycuID", "txtName", "mail"]
        return all(field in data for field in required_fields)
    
    def _get_test_portal_data(self) -> Dict:
        """Return test portal data for development"""
        return {
            "iat": int(datetime.now().timestamp()),
            "txtID": "test_user",
            "nycuID": "test_user",
            "txtName": "Test User",
            "idno": "A123456789",
            "mail": "test.user@nycu.edu.tw",
            "dept": "資訊工程學系",
            "deptCode": "5743",
            "userType": "student",
            "oldEmpNo": "test_user",
            "employeestatus": "在學"
        }
    
    async def process_portal_login(self, token: str) -> Dict:
        """
        Complete portal SSO login process
        
        Args:
            token: JWT token from Portal
            
        Returns:
            Dict containing access token and user information
        """
        # Verify token with Portal JWT server
        portal_data = await self.verify_portal_token(token)
        
        # Extract user information
        nycu_id = portal_data.get("txtID") or portal_data.get("nycuID")
        name = portal_data.get("txtName")
        email = portal_data.get("mail")
        dept_name = portal_data.get("dept")
        dept_code = portal_data.get("deptCode")
        user_type = portal_data.get("userType", "student")
        status = portal_data.get("employeestatus", "在學")
        
        if not nycu_id or not name or not email:
            raise AuthenticationError("Incomplete user data from Portal")
        
        # Find or create user
        user = await self._find_or_create_user(
            nycu_id=nycu_id,
            name=name,
            email=email,
            dept_name=dept_name,
            dept_code=dept_code,
            user_type=user_type,
            status=status,
            raw_data=portal_data
        )
        
        # Update last login time
        user.last_login_at = datetime.utcnow()
        await self.db.commit()
        
        # Generate system tokens
        token_response = await self.auth_service.create_tokens(user)
        
        return {
            "access_token": token_response.access_token,
            "token_type": token_response.token_type,
            "expires_in": token_response.expires_in,
            "user": token_response.user.model_dump()
        }
    
    async def _find_or_create_user(
        self,
        nycu_id: str,
        name: str,
        email: str,
        dept_name: Optional[str] = None,
        dept_code: Optional[str] = None,
        user_type: str = "student",
        status: str = "在學",
        raw_data: Optional[Dict] = None
    ) -> User:
        """Find existing user or create new one"""
        
        # Try to find existing user by NYCU ID
        stmt = select(User).where(User.nycu_id == nycu_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            # Update existing user data
            user.name = name
            user.email = email
            if dept_name:
                user.dept_name = dept_name
            if dept_code:
                user.dept_code = dept_code
            user.raw_data = raw_data
            return user
        
        # Create new user
        user_role = self._map_user_type_to_role(user_type)
        user_type_enum = self._map_user_type_to_enum(user_type)
        user_status_enum = self._map_status_to_enum(status)
        
        new_user = User(
            nycu_id=nycu_id,
            name=name,
            email=email,
            role=user_role,
            user_type=user_type_enum,
            status=user_status_enum,
            dept_name=dept_name,
            dept_code=dept_code,
            raw_data=raw_data
        )
        
        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)
        
        logger.info(f"Created new user from Portal SSO: {nycu_id} ({name})")
        return new_user
    
    def _map_user_type_to_role(self, user_type: str) -> UserRole:
        """Map Portal userType to system UserRole"""
        type_mapping = {
            "student": UserRole.STUDENT,
            "employee": UserRole.PROFESSOR,  # Default employees to professor
            "staff": UserRole.ADMIN,
        }
        return type_mapping.get(user_type.lower(), UserRole.STUDENT)
    
    def _map_user_type_to_enum(self, user_type: str) -> UserType:
        """Map Portal userType to system UserType enum"""
        type_mapping = {
            "student": UserType.STUDENT,
            "employee": UserType.EMPLOYEE,
            "staff": UserType.EMPLOYEE,
        }
        return type_mapping.get(user_type.lower(), UserType.STUDENT)
    
    def _map_status_to_enum(self, status: str) -> EmployeeStatus:
        """Map Portal status to system UserStatus enum"""
        status_mapping = {
            "在學": EmployeeStatus.STUDENT,
            "在職": EmployeeStatus.ACTIVE,
            "退休": EmployeeStatus.RETIRED,
            "畢業": EmployeeStatus.GRADUATED,
        }
        return status_mapping.get(status, EmployeeStatus.STUDENT)