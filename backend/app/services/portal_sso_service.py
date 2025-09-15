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
from app.services.student_service import StudentService

logger = logging.getLogger(__name__)


class PortalSSOService:
    """Portal SSO service for NYCU Portal integration"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.auth_service = AuthService(db)
        self.student_service = StudentService()
    
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
                # Portal expects form data, not JSON
                # Try multiple parameter combinations that Portal might expect
                logger.info(f"Attempting Portal JWT verification with token: {token[:50]}...")
                
                # First attempt: just the token
                response = await client.post(
                    settings.portal_jwt_server_url,
                    data={"token": token},  # Try 'token' parameter name
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                # If that fails, try alternative parameter names
                if response.status_code == 406:
                    logger.info("First attempt failed, trying 'jwt' parameter name...")
                    response = await client.post(
                        settings.portal_jwt_server_url,
                        data={"jwt": token},
                        headers={"Content-Type": "application/x-www-form-urlencoded"}
                    )
                    
                # If still fails, try with additional context
                if response.status_code == 406:
                    logger.info("Second attempt failed, trying with callback URL...")
                    response = await client.post(
                        settings.portal_jwt_server_url,
                        data={
                            "token": token,
                            "callback_url": "https://140.113.7.148/api/v1/auth/portal-sso/verify"
                        },
                        headers={"Content-Type": "application/x-www-form-urlencoded"}
                    )
                
                if response.status_code != 200:
                    logger.error(f"Portal JWT verification failed: {response.status_code} - {response.text}")
                    raise AuthenticationError(f"Portal token verification failed: {response.status_code}")
                
                portal_data = response.json()
                
                # Validate portal response format
                if portal_data.get("status") == "true" and "data" in portal_data:
                    # Extract user data from nested structure
                    user_data = portal_data["data"]
                    if not self._validate_portal_response(user_data):
                        logger.error(f"Invalid user data in portal response: {user_data}")
                        raise AuthenticationError("Invalid user data format")
                    return user_data
                else:
                    logger.error(f"Invalid portal response format: {portal_data}")
                    raise AuthenticationError("Invalid portal response format")
                
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
        # Only require essential fields, mail can be None
        required_fields = ["txtID", "nycuID", "txtName"]
        return all(field in data and data[field] for field in required_fields)
    
    async def _verify_student_status(self, nycu_id: str) -> tuple[bool, Optional[Dict]]:
        """
        Verify if user is a student using Student API
        
        Args:
            nycu_id: NYCU ID to verify
            
        Returns:
            tuple: (is_student, student_data)
        """
        try:
            if not self.student_service.api_enabled:
                logger.warning("Student API is disabled, cannot verify student status")
                return False, None
                
            # Try to get student data from the API
            student_data = await self.student_service.get_student_basic_info(nycu_id)
            
            if student_data:
                logger.info(f"User {nycu_id} verified as student via Student API")
                return True, student_data
            else:
                logger.info(f"User {nycu_id} not found in Student API")
                return False, None
                
        except Exception as e:
            logger.error(f"Error verifying student status for {nycu_id}: {str(e)}")
            return False, None
    
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
        portal_user_type = portal_data.get("userType", "student")  # Portal's claimed user type
        status = portal_data.get("employeestatus", "在學")
        
        if not nycu_id or not name:
            raise AuthenticationError("Incomplete user data from Portal")
        
        # Verify actual student status using Student API (don't rely on Portal's dept)
        is_student, student_data = await self._verify_student_status(nycu_id)
        
        # Determine actual user type and role based on Student API verification
        if is_student:
            user_type = "student"
            user_role = UserRole.STUDENT
            mapped_user_type = UserType.STUDENT
            logger.info(f"User {nycu_id} confirmed as student via Student API")
        else:
            # Not a student according to Student API, use Portal's classification
            user_type = portal_user_type
            if portal_user_type.lower() in ["employee", "staff", "teacher"]:
                user_role = UserRole.PROFESSOR  # Default employees to professor
                mapped_user_type = UserType.EMPLOYEE
            elif portal_user_type.lower() == "admin":
                user_role = UserRole.ADMIN
                mapped_user_type = UserType.EMPLOYEE
            else:
                # Fallback to student if uncertain
                user_role = UserRole.STUDENT
                mapped_user_type = UserType.STUDENT
            logger.info(f"User {nycu_id} classified as {user_type} based on Portal data")
        
        # Generate email if not provided
        if not email:
            email = f"{nycu_id}@nycu.edu.tw"
        
        # Find or create user
        user = await self._find_or_create_user(
            nycu_id=nycu_id,
            name=name,
            email=email,
            dept_name=dept_name,
            dept_code=dept_code,
            user_type=mapped_user_type,
            user_role=user_role,
            status=status,
            raw_data=portal_data,
            student_data=student_data
        )
        
        # Update last login time
        user.last_login_at = datetime.utcnow()
        await self.db.commit()
        
        # Generate system tokens with debug data
        logger.info(f"🔍 Creating tokens with debug data - Portal: {bool(portal_data)}, Student: {bool(student_data)}")
        if portal_data:
            logger.debug(f"🔍 Portal data keys: {list(portal_data.keys())}")
        if student_data:
            logger.debug(f"🔍 Student data keys: {list(student_data.keys())}")
            
        token_response = await self.auth_service.create_tokens(
            user, 
            portal_data=portal_data, 
            student_data=student_data
        )
        
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
        user_type: UserType = UserType.STUDENT,
        user_role: UserRole = UserRole.STUDENT,
        status: str = "在學",
        raw_data: Optional[Dict] = None,
        student_data: Optional[Dict] = None
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
            user.role = user_role  # Update role based on Student API verification
            user.user_type = user_type  # Update user type based on verification
            if dept_name:
                user.dept_name = dept_name
            if dept_code:
                user.dept_code = dept_code
            user.raw_data = raw_data
            # Store student data if available
            if student_data:
                if user.raw_data:
                    user.raw_data["student_api_data"] = student_data
                else:
                    user.raw_data = {"student_api_data": student_data}
            logger.info(f"Updated existing user {nycu_id} with role {user_role.value}")
            return user
        
        # Create new user  
        user_status_enum = self._map_status_to_enum(status)
        
        # Prepare raw data with student information
        combined_raw_data = raw_data or {}
        if student_data:
            combined_raw_data["student_api_data"] = student_data
        
        new_user = User(
            nycu_id=nycu_id,
            name=name,
            email=email,
            role=user_role,
            user_type=user_type,
            status=user_status_enum,
            dept_name=dept_name,
            dept_code=dept_code,
            raw_data=combined_raw_data
        )
        
        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)
        
        logger.info(f"Created new user from Portal SSO: {nycu_id} ({name}) with role {user_role.value}")
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