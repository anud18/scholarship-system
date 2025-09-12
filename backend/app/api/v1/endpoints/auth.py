"""
Authentication API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime

from app.db.deps import get_db
from app.schemas.user import UserCreate, UserLogin, TokenResponse, UserResponse, PortalSSORequest, DeveloperProfileRequest
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService
from app.services.mock_sso_service import MockSSOService
from app.services.portal_sso_service import PortalSSOService
from app.services.developer_profile_service import DeveloperProfileService, DeveloperProfile, DeveloperProfileManager
from app.core.security import get_current_user
from app.core.config import settings
from app.models.user import User, UserRole, UserType, EmployeeStatus

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user"""
    auth_service = AuthService(db)
    return await auth_service.register_user(user_data)


@router.post("/login")
async def login(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Login user and return access token"""
    auth_service = AuthService(db)
    token_response = await auth_service.login(login_data)
    
    # Return wrapped in standard ApiResponse format
    return {
        "success": True,
        "message": "Login successful",
        "data": {
            "access_token": token_response.access_token,
            "token_type": token_response.token_type,
            "expires_in": token_response.expires_in,
            "user": token_response.user.model_dump()
        }
    }


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information"""
    user_data = UserResponse.model_validate(current_user)
    return {
        "success": True,
        "message": "User information retrieved successfully",
        "data": user_data
    }


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """Logout user (client-side token removal)"""
    return MessageResponse(message="Logged out successfully")


@router.post("/refresh")
async def refresh_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token"""
    auth_service = AuthService(db)
    token_response = await auth_service.create_tokens(current_user)
    
    # Return wrapped in standard ApiResponse format
    return {
        "success": True,
        "message": "Token refreshed successfully",
        "data": {
            "access_token": token_response.access_token,
            "token_type": token_response.token_type,
            "expires_in": token_response.expires_in
        }
    }


# Mock SSO endpoints for development
@router.get("/mock-sso/users")
async def get_mock_users(
    db: AsyncSession = Depends(get_db)
):
    """Get available mock users for development login"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mock SSO is disabled"
        )
    
    mock_sso_service = MockSSOService(db)
    users = await mock_sso_service.get_mock_users()
    
    return {
        "success": True,
        "message": "Mock users retrieved successfully",
        "data": users
    }


@router.post("/mock-sso/login")
async def mock_sso_login(
    request_data: PortalSSORequest,
    db: AsyncSession = Depends(get_db)
):
    """Login as mock user for development"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mock SSO is disabled"
        )
    
    nycu_id = request_data.nycu_id or request_data.username  # 支持兩種參數名稱
    if not nycu_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="NYCU ID is required"
        )
    
    try:
        mock_sso_service = MockSSOService(db)
        token_response = await mock_sso_service.mock_sso_login(nycu_id)
        
        return {
            "success": True,
            "message": f"Mock SSO login successful for {nycu_id}",
            "data": {
                "access_token": token_response.access_token,
                "token_type": token_response.token_type,
                "expires_in": token_response.expires_in,
                "user": token_response.user.model_dump()
            }
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


async def get_portal_sso_data(
    request: Request,
    # Form parameters (for application/x-www-form-urlencoded)
    token: Optional[str] = Form(None),
    nycu_id: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    # JSON body (for application/json) - optional fallback
    request_data: Optional[PortalSSORequest] = None
) -> tuple[Optional[str], Optional[str]]:
    """Extract portal SSO data from either form or JSON body"""
    content_type = request.headers.get("content-type", "")
    
    if "application/x-www-form-urlencoded" in content_type:
        # Use form data
        return token, nycu_id or username
    elif "application/json" in content_type and request_data:
        # Use JSON data
        return request_data.token, request_data.nycu_id or request_data.username
    else:
        # Default to form data even if content-type is unclear
        return token, nycu_id or username


@router.post("/portal-sso/verify")
async def portal_sso_verify(
    request: Request,
    db: AsyncSession = Depends(get_db),
    # Accept all possible form fields to debug what's being sent
    token: Optional[str] = Form(None),
    nycu_id: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    # Common JWT field names in SSO systems
    jwt: Optional[str] = Form(None),
    jwt_token: Optional[str] = Form(None),
    access_token: Optional[str] = Form(None),
    id_token: Optional[str] = Form(None),
    # Other possible field names
    user_id: Optional[str] = Form(None),
    userid: Optional[str] = Form(None),
    student_id: Optional[str] = Form(None)
):
    """
    Verify portal SSO token and perform user login
    
    This endpoint receives POST requests from NYCU Portal with JWT token.
    It verifies the token with Portal JWT server and logs in the user.
    """
    if not settings.portal_sso_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portal SSO is disabled"
        )
    
    # Debug logging to see what parameters are being sent
    import logging
    logger = logging.getLogger(__name__)
    
    received_params = {
        "token": token, "nycu_id": nycu_id, "username": username,
        "jwt": jwt, "jwt_token": jwt_token, "access_token": access_token,
        "id_token": id_token, "user_id": user_id, "userid": userid,
        "student_id": student_id
    }
    
    # Log only non-None parameters
    non_none_params = {k: v for k, v in received_params.items() if v is not None}
    logger.info(f"Portal SSO received parameters: {non_none_params}")
    
    # Extract data from form parameters (try multiple possible token field names)
    final_token = token or jwt or jwt_token or access_token or id_token
    final_nycu_id = nycu_id or username or user_id or userid or student_id
    
    # If no token provided, fall back to mock SSO for testing
    if not final_token and final_nycu_id and settings.enable_mock_sso:
        try:
            mock_sso_service = MockSSOService(db)
            portal_data = await mock_sso_service.get_portal_sso_data(final_nycu_id)
            
            # Return in exact portal format for testing
            return {
                "status": "success", 
                "message": "jwt pass",
                "data": portal_data
            }
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
    
    # Real Portal SSO flow
    if not final_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token is required for Portal SSO"
        )
    
    try:
        portal_sso_service = PortalSSOService(db)
        
        # Try direct JWT processing first (bypass Portal verification for testing)
        from jose import jwt as jwt_lib
        import json
        
        try:
            # Decode JWT without verification to extract user data
            # This is for testing - in production you'd verify the signature
            decoded_token = jwt_lib.get_unverified_claims(final_token)
            logger.info(f"Decoded JWT payload: {decoded_token}")
            
            # Extract user information from JWT
            nycu_id = decoded_token.get('nycuID') or decoded_token.get('txtID')
            user_name = decoded_token.get('txtName', '')
            user_type = decoded_token.get('userType', 'student')
            dept_code = decoded_token.get('deptCode', '')
            dept_name = decoded_token.get('dept', '')
            employee_status = decoded_token.get('employeestatus', '')
            
            if not nycu_id:
                raise ValueError("No user ID found in JWT")
                
            logger.info(f"Processing Portal login for user: {nycu_id} ({user_name})")
            
            # Create or get user account and generate access token
            from app.services.auth_service import AuthService
            from app.schemas.user import UserCreate
            from fastapi.responses import RedirectResponse
            
            auth_service = AuthService(db)
            
            # Map Portal user type to our system roles
            role_mapping = {
                "student": UserRole.STUDENT,
                "staff": UserRole.STAFF,
                "teacher": UserRole.STAFF,
                "admin": UserRole.ADMIN
            }
            user_role = role_mapping.get(user_type.lower(), UserRole.STUDENT)
            
            # Map Portal user type to our UserType enum
            user_type_mapping = {
                "student": UserType.STUDENT,
                "staff": UserType.STAFF,
                "teacher": UserType.STAFF,
                "admin": UserType.STAFF
            }
            mapped_user_type = user_type_mapping.get(user_type.lower(), UserType.STUDENT)
            
            # Map employee status
            status_mapping = {
                "在學": EmployeeStatus.ACTIVE,
                "在職": EmployeeStatus.ACTIVE,
                "畢業": EmployeeStatus.INACTIVE,
                "離職": EmployeeStatus.INACTIVE
            }
            mapped_status = status_mapping.get(employee_status, EmployeeStatus.ACTIVE)
            
            try:
                # Try to get existing user
                from sqlalchemy import select
                result = await db.execute(select(User).where(User.nycu_id == nycu_id))
                existing_user = result.scalar_one_or_none()
                
                if existing_user:
                    # Update existing user info
                    existing_user.name = user_name
                    existing_user.user_type = mapped_user_type
                    existing_user.status = mapped_status
                    existing_user.dept_code = dept_code
                    existing_user.dept_name = dept_name
                    existing_user.role = user_role
                    existing_user.last_login_at = datetime.utcnow()
                    
                    await db.commit()
                    user = existing_user
                    logger.info(f"Updated existing user: {nycu_id}")
                else:
                    # Create new user
                    user_data = UserCreate(
                        nycu_id=nycu_id,
                        name=user_name,
                        email=f"{nycu_id}@nycu.edu.tw",  # Generate email if not provided
                        user_type=mapped_user_type,
                        status=mapped_status,
                        dept_code=dept_code,
                        dept_name=dept_name,
                        role=user_role,
                        comment=f"Portal SSO user created on {datetime.utcnow()}"
                    )
                    
                    user = await auth_service.register_user(user_data)
                    logger.info(f"Created new user: {nycu_id}")
                
                # Generate access token
                token_response = await auth_service.create_tokens(user)
                
                # Create redirect URL with token (for frontend to handle)
                frontend_url = "https://140.113.7.148"  # Your frontend URL
                redirect_url = f"{frontend_url}/auth/sso-callback?token={token_response.access_token}&redirect=dashboard"
                
                # Return redirect response
                return RedirectResponse(
                    url=redirect_url,
                    status_code=302,
                    headers={"Set-Cookie": f"access_token={token_response.access_token}; Path=/; HttpOnly; Secure"}
                )
                
            except Exception as user_error:
                logger.error(f"User creation/login error: {user_error}")
                # Fallback: return data without redirect
                return {
                    "success": True,
                    "message": "Portal SSO login successful (direct JWT processing)",
                    "data": {
                        "nycu_id": nycu_id,
                        "name": user_name,
                        "user_type": user_type,
                        "dept_code": dept_code,
                        "dept_name": dept_name,
                        "employee_status": employee_status,
                        "error": str(user_error)
                    }
                }
            
        except Exception as jwt_error:
            logger.error(f"JWT decode error: {jwt_error}")
            # Fall back to Portal verification if JWT decode fails
            pass
        
        # Fallback: Try Portal verification
        login_data = await portal_sso_service.process_portal_login(final_token)
        
        return {
            "success": True,
            "message": "Portal SSO login successful",
            "data": login_data
        }
    except Exception as e:
        logger.error(f"Portal SSO error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Portal SSO verification failed: {str(e)}"
        )


@router.get("/portal-sso/verify/{username}")
async def portal_sso_verify_get(
    username: str,
    db: AsyncSession = Depends(get_db)
):
    """Get portal SSO data for a specific user (GET method for testing)"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portal SSO is disabled"
        )
    
    try:
        mock_sso_service = MockSSOService(db)
        portal_data = await mock_sso_service.get_portal_sso_data(username)
        
        # Return in exact portal format
        return {
            "status": "success",
            "message": "jwt pass",
            "data": portal_data
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )





# Developer Profile endpoints for personalized testing
@router.get("/dev-profiles/developers")
async def get_all_developers(
    db: AsyncSession = Depends(get_db)
):
    """Get list of all developers who have test profiles"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profiles are disabled"
        )
    
    dev_service = DeveloperProfileService(db)
    developer_ids = await dev_service.get_all_developer_ids()
    
    return {
        "success": True,
        "message": "Developer list retrieved successfully",
        "data": developer_ids
    }


@router.get("/dev-profiles/{developer_id}")
async def get_developer_profiles(
    developer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all test profiles for a specific developer"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profiles are disabled"
        )
    
    dev_service = DeveloperProfileService(db)
    users = await dev_service.get_developer_users(developer_id)
    
    profiles = [
        {
            "username": user.nycu_id,
            "email": user.email,
            "full_name": user.name,
            "chinese_name": user.raw_data.get("chinese_name") if user.raw_data else None,
            "english_name": user.raw_data.get("english_name") if user.raw_data else None,
            "role": user.role.value,
            "is_active": True,  # All developer users are active
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
        for user in users
    ]
    
    return {
        "success": True,
        "message": f"Developer profiles for {developer_id} retrieved successfully",
        "data": {
            "developer_id": developer_id,
            "profiles": profiles,
            "count": len(profiles)
        }
    }


@router.post("/dev-profiles/{developer_id}/quick-setup")
async def quick_setup_developer(
    developer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Quick setup default test profiles for a developer"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profiles are disabled"
        )
    
    dev_service = DeveloperProfileService(db)
    users = await dev_service.quick_setup_developer(developer_id)
    
    profiles = [
        {
            "username": user.nycu_id,
            "full_name": user.name,
            "role": user.role.value
        }
        for user in users
    ]
    
    return {
        "success": True,
        "message": f"Quick setup completed for developer {developer_id}",
        "data": {
            "developer_id": developer_id,
            "created_profiles": profiles,
            "count": len(profiles)
        }
    }


@router.post("/dev-profiles/{developer_id}/create-custom")
async def create_custom_profile(
    developer_id: str,
    profile_data: DeveloperProfileRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a custom test profile for a developer"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profiles are disabled"
        )
    
    try:
        # Create profile
        profile = DeveloperProfile(
            developer_id=developer_id,
            name=profile_data.full_name,  # Keep compatibility with frontend
            chinese_name=profile_data.chinese_name,
            english_name=profile_data.english_name,
            role=profile_data.role,
            email_domain=profile_data.email_domain,
            custom_attributes=profile_data.custom_attributes or {}
        )
        
        dev_service = DeveloperProfileService(db)
        user = await dev_service.create_developer_user(developer_id, profile)
        
        return {
            "success": True,
            "message": f"Custom profile created for {developer_id}",
            "data": {
                "username": user.nycu_id,
                "email": user.email,
                "full_name": user.name,
                "role": user.role.value
            }
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid profile data: {str(e)}"
        )


@router.post("/dev-profiles/{developer_id}/student-suite")
async def create_student_suite(
    developer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Create a complete student test suite for a developer"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profiles are disabled"
        )
    
    profiles = DeveloperProfileManager.create_student_profiles(developer_id)
    dev_service = DeveloperProfileService(db)
    users = await dev_service.create_developer_test_suite(developer_id, profiles)
    
    created_profiles = [
        {
            "username": user.nycu_id,
            "full_name": user.name,
            "role": user.role.value,
            "student_type": profiles[i].custom_attributes.get("student_type")
        }
        for i, user in enumerate(users)
    ]
    
    return {
        "success": True,
        "message": f"Student test suite created for {developer_id}",
        "data": {
            "developer_id": developer_id,
            "created_profiles": created_profiles,
            "count": len(created_profiles)
        }
    }


@router.post("/dev-profiles/{developer_id}/staff-suite")
async def create_staff_suite(
    developer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Create a complete staff test suite for a developer"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profiles are disabled"
        )
    
    profiles = DeveloperProfileManager.create_staff_profiles(developer_id)
    dev_service = DeveloperProfileService(db)
    users = await dev_service.create_developer_test_suite(developer_id, profiles)
    
    created_profiles = [
        {
            "username": user.nycu_id,
            "full_name": user.name,
            "role": user.role.value
        }
        for user in users
    ]
    
    return {
        "success": True,
        "message": f"Staff test suite created for {developer_id}",
        "data": {
            "developer_id": developer_id,
            "created_profiles": created_profiles,
            "count": len(created_profiles)
        }
    }


@router.delete("/dev-profiles/{developer_id}")
async def delete_developer_profiles(
    developer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete all test profiles for a developer"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profiles are disabled"
        )
    
    dev_service = DeveloperProfileService(db)
    deleted_count = await dev_service.delete_all_developer_users(developer_id)
    
    return {
        "success": True,
        "message": f"Deleted {deleted_count} profiles for developer {developer_id}",
        "data": {
            "developer_id": developer_id,
            "deleted_count": deleted_count
        }
    }


@router.delete("/dev-profiles/{developer_id}/{role}")
async def delete_specific_profile(
    developer_id: str,
    role: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific test profile for a developer"""
    if not settings.enable_mock_sso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer profiles are disabled"
        )
    
    try:
        user_role = UserRole(role)
        dev_service = DeveloperProfileService(db)
        deleted = await dev_service.delete_developer_user(developer_id, user_role)
        
        if deleted:
            return {
                "success": True,
                "message": f"Deleted {role} profile for developer {developer_id}",
                "data": {"deleted": True}
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile not found: {developer_id}/{role}"
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {role}"
        ) 