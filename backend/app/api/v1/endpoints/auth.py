"""
Authentication API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db
from app.schemas.user import UserCreate, UserLogin, TokenResponse, UserResponse, PortalSSORequest, DeveloperProfileRequest
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService
from app.services.mock_sso_service import MockSSOService
from app.services.portal_sso_service import PortalSSOService
from app.services.developer_profile_service import DeveloperProfileService, DeveloperProfile, DeveloperProfileManager
from app.core.security import get_current_user
from app.core.config import settings
from app.models.user import User, UserRole

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


@router.post("/portal-sso/verify")
async def portal_sso_verify(
    token: str = Form(None),
    nycu_id: str = Form(None),
    username: str = Form(None),
    db: AsyncSession = Depends(get_db)
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
    
    # Handle both real Portal tokens and mock/test data
    nycu_id = nycu_id or username
    
    # If no token provided, fall back to mock SSO for testing
    if not token and nycu_id and settings.enable_mock_sso:
        try:
            mock_sso_service = MockSSOService(db)
            portal_data = await mock_sso_service.get_portal_sso_data(nycu_id)
            
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
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token is required for Portal SSO"
        )
    
    try:
        portal_sso_service = PortalSSOService(db)
        login_data = await portal_sso_service.process_portal_login(token)
        
        return {
            "success": True,
            "message": "Portal SSO login successful",
            "data": login_data
        }
    except Exception as e:
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