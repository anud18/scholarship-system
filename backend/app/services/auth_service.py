"""
Authentication service for user login and registration
"""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import create_access_token, create_refresh_token
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserLogin, TokenResponse, UserResponse


class AuthService:
    """Authentication service"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def register_user(self, user_data: UserCreate) -> UserResponse:
        """Register a new user"""
        # Check if email already exists
        stmt = select(User).where(User.email == user_data.email)
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            raise ConflictError("Email already registered")
        
        # Check if nycu_id already exists
        stmt = select(User).where(User.nycu_id == user_data.nycu_id)
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            raise ConflictError("NYCU ID already exists")
        
        # Create new user
        user = User(
            nycu_id=user_data.nycu_id,
            name=user_data.name,
            email=user_data.email,
            user_type=user_data.user_type,
            status=user_data.status,
            dept_code=user_data.dept_code,
            dept_name=user_data.dept_name,
            role=user_data.role
        )
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        return UserResponse.model_validate(user)
    
    async def authenticate_user(self, login_data: UserLogin) -> User:
        """Authenticate user with nycu_id/email"""
        # Try to find user by nycu_id or email
        stmt = select(User).where(
            (User.nycu_id == login_data.username) | (User.email == login_data.username)
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise AuthenticationError("Invalid nycu_id or email")
        
        # Update last login time
        user.last_login_at = datetime.utcnow()
        await self.db.commit()
        
        return user
    
    async def create_tokens(self, user: User) -> TokenResponse:
        """Create access and refresh tokens for user"""
        token_data = {"sub": str(user.id), "nycu_id": user.nycu_id, "role": user.role.value}
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=3600,  # 1 hour
            user=UserResponse.model_validate(user)
        )
    
    async def login(self, login_data: UserLogin) -> TokenResponse:
        """Complete login flow"""
        user = await self.authenticate_user(login_data)
        return await self.create_tokens(user)
    
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        return await self.db.get(User, user_id)
    
    async def get_user_by_nycu_id(self, nycu_id: str) -> Optional[User]:
        """Get user by nycu_id"""
        stmt = select(User).where(User.nycu_id == nycu_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user (alias for register_user)"""
        return await self.register_user(user_data)
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() 