"""
Unit tests for core security utilities
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt

from app.core.security import (
    create_access_token, create_refresh_token, verify_token,
    get_current_user, require_role, require_roles,
    require_admin, require_super_admin, require_student,
    require_professor, require_college, require_staff
)
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.models.user import User, UserRole


class TestTokenOperations:
    """Test cases for JWT token operations"""

    @patch('app.core.security.settings')
    def test_create_access_token_default_expiry(self, mock_settings):
        """Test creating access token with default expiry"""
        mock_settings.secret_key = "test_secret"
        mock_settings.algorithm = "HS256"
        mock_settings.access_token_expire_minutes = 30
        
        data = {"sub": "123", "role": "student"}
        
        with patch('app.core.security.datetime') as mock_datetime:
            mock_now = datetime(2024, 1, 1, 12, 0, 0)
            mock_datetime.utcnow.return_value = mock_now
            
            token = create_access_token(data)
            
            # Verify token can be decoded
            payload = jwt.decode(token, "test_secret", algorithms=["HS256"])
            assert payload["sub"] == "123"
            assert payload["role"] == "student"
            assert payload["exp"] == int((mock_now + timedelta(minutes=30)).timestamp())

    @patch('app.core.security.settings')
    def test_create_access_token_custom_expiry(self, mock_settings):
        """Test creating access token with custom expiry"""
        mock_settings.secret_key = "test_secret"
        mock_settings.algorithm = "HS256"
        
        data = {"sub": "123"}
        expires_delta = timedelta(hours=2)
        
        with patch('app.core.security.datetime') as mock_datetime:
            mock_now = datetime(2024, 1, 1, 12, 0, 0)
            mock_datetime.utcnow.return_value = mock_now
            
            token = create_access_token(data, expires_delta)
            
            # Verify token can be decoded
            payload = jwt.decode(token, "test_secret", algorithms=["HS256"])
            assert payload["sub"] == "123"
            assert payload["exp"] == int((mock_now + expires_delta).timestamp())

    @patch('app.core.security.settings')
    def test_create_refresh_token(self, mock_settings):
        """Test creating refresh token"""
        mock_settings.secret_key = "test_secret"
        mock_settings.algorithm = "HS256"
        mock_settings.refresh_token_expire_days = 7
        
        data = {"sub": "123", "role": "student"}
        
        with patch('app.core.security.datetime') as mock_datetime:
            mock_now = datetime(2024, 1, 1, 12, 0, 0)
            mock_datetime.utcnow.return_value = mock_now
            
            token = create_refresh_token(data)
            
            # Verify token can be decoded
            payload = jwt.decode(token, "test_secret", algorithms=["HS256"])
            assert payload["sub"] == "123"
            assert payload["role"] == "student"
            assert payload["type"] == "refresh"
            assert payload["exp"] == int((mock_now + timedelta(days=7)).timestamp())

    @patch('app.core.security.settings')
    def test_verify_token_success(self, mock_settings):
        """Test successful token verification"""
        mock_settings.secret_key = "test_secret"
        mock_settings.algorithm = "HS256"
        
        # Create a valid token
        data = {"sub": "123", "role": "student"}
        token = jwt.encode(data, "test_secret", algorithm="HS256")
        
        payload = verify_token(token)
        
        assert payload["sub"] == "123"
        assert payload["role"] == "student"

    @patch('app.core.security.settings')
    def test_verify_token_invalid(self, mock_settings):
        """Test token verification with invalid token"""
        mock_settings.secret_key = "test_secret"
        mock_settings.algorithm = "HS256"
        
        invalid_token = "invalid.token.here"
        
        with pytest.raises(AuthenticationError, match="Invalid token"):
            verify_token(invalid_token)

    @patch('app.core.security.settings')
    def test_verify_token_expired(self, mock_settings):
        """Test token verification with expired token"""
        mock_settings.secret_key = "test_secret"
        mock_settings.algorithm = "HS256"
        
        # Create an expired token
        past_time = datetime.utcnow() - timedelta(hours=1)
        data = {"sub": "123", "exp": past_time}
        expired_token = jwt.encode(data, "test_secret", algorithm="HS256")
        
        with pytest.raises(AuthenticationError, match="Token has expired"):
            verify_token(expired_token)

    @patch('app.core.security.settings')
    def test_verify_token_wrong_secret(self, mock_settings):
        """Test token verification with wrong secret"""
        mock_settings.secret_key = "correct_secret"
        mock_settings.algorithm = "HS256"
        
        # Create token with different secret
        data = {"sub": "123"}
        token = jwt.encode(data, "wrong_secret", algorithm="HS256")
        
        with pytest.raises(AuthenticationError, match="Invalid token"):
            verify_token(token)


class TestUserAuthentication:
    """Test cases for user authentication"""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self):
        """Test successful user authentication"""
        # Mock dependencies
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid_token")
        mock_db = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)
        mock_user.id = 123
        
        with patch('app.core.security.verify_token') as mock_verify, \
             patch.object(mock_db, 'get') as mock_get:
            
            # Mock token verification
            mock_verify.return_value = {"sub": "123", "role": "student"}
            mock_get.return_value = mock_user
            
            result = await get_current_user(credentials, mock_db)
            
            # Verify token was verified
            mock_verify.assert_called_once_with("valid_token")
            
            # Verify user was fetched from database
            mock_get.assert_called_once_with(User, 123)
            
            assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self):
        """Test user authentication when no credentials provided"""
        mock_db = Mock(spec=AsyncSession)
        
        with pytest.raises(AuthenticationError, match="Authorization header missing"):
            await get_current_user(None, mock_db)

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Test user authentication with invalid token"""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid_token")
        mock_db = Mock(spec=AsyncSession)
        
        with patch('app.core.security.verify_token') as mock_verify:
            mock_verify.side_effect = AuthenticationError("Invalid token")
            
            with pytest.raises(AuthenticationError, match="Invalid token"):
                await get_current_user(credentials, mock_db)

    @pytest.mark.asyncio
    async def test_get_current_user_no_sub_in_token(self):
        """Test user authentication when token has no 'sub' claim"""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token_without_sub")
        mock_db = Mock(spec=AsyncSession)
        
        with patch('app.core.security.verify_token') as mock_verify:
            mock_verify.return_value = {"role": "student"}  # No 'sub' claim
            
            with pytest.raises(AuthenticationError, match="Invalid token"):
                await get_current_user(credentials, mock_db)

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_user_id(self):
        """Test user authentication with invalid user ID format"""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token_invalid_sub")
        mock_db = Mock(spec=AsyncSession)
        
        with patch('app.core.security.verify_token') as mock_verify:
            mock_verify.return_value = {"sub": "not_a_number"}
            
            with pytest.raises(AuthenticationError, match="Could not validate credentials"):
                await get_current_user(credentials, mock_db)

    @pytest.mark.asyncio
    async def test_get_current_user_user_not_found(self):
        """Test user authentication when user not found in database"""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid_token")
        mock_db = Mock(spec=AsyncSession)
        
        with patch('app.core.security.verify_token') as mock_verify, \
             patch.object(mock_db, 'get') as mock_get:
            
            mock_verify.return_value = {"sub": "999"}
            mock_get.return_value = None  # User not found
            
            with pytest.raises(AuthenticationError, match="User not found"):
                await get_current_user(credentials, mock_db)


class TestRoleBasedAccess:
    """Test cases for role-based access control"""

    def test_require_role_success(self):
        """Test successful role requirement check"""
        mock_user = Mock(spec=User)
        mock_user.has_role.return_value = True
        
        role_checker = require_role(UserRole.STUDENT)
        result = role_checker(mock_user)
        
        mock_user.has_role.assert_called_once_with(UserRole.STUDENT)
        assert result == mock_user

    def test_require_role_failure(self):
        """Test role requirement check failure"""
        mock_user = Mock(spec=User)
        mock_user.has_role.return_value = False
        
        role_checker = require_role(UserRole.ADMIN)
        
        with pytest.raises(AuthorizationError, match="Access denied. Required role: admin"):
            role_checker(mock_user)

    def test_require_roles_success_first_role(self):
        """Test successful multiple roles check (first role matches)"""
        mock_user = Mock(spec=User)
        mock_user.has_role.side_effect = [True, False]  # First role matches
        
        roles_checker = require_roles(UserRole.ADMIN, UserRole.PROFESSOR)
        result = roles_checker(mock_user)
        
        assert result == mock_user

    def test_require_roles_success_second_role(self):
        """Test successful multiple roles check (second role matches)"""
        mock_user = Mock(spec=User)
        mock_user.has_role.side_effect = [False, True]  # Second role matches
        
        roles_checker = require_roles(UserRole.ADMIN, UserRole.PROFESSOR)
        result = roles_checker(mock_user)
        
        assert result == mock_user

    def test_require_roles_failure(self):
        """Test multiple roles check failure"""
        mock_user = Mock(spec=User)
        mock_user.has_role.return_value = False  # No roles match
        
        roles_checker = require_roles(UserRole.ADMIN, UserRole.PROFESSOR)
        
        with pytest.raises(AuthorizationError, match="Access denied. Required roles: admin, professor"):
            roles_checker(mock_user)

    def test_require_admin_success_admin(self):
        """Test successful admin requirement (admin user)"""
        mock_user = Mock(spec=User)
        mock_user.is_admin.return_value = True
        mock_user.is_super_admin.return_value = False
        
        result = require_admin(mock_user)
        
        assert result == mock_user

    def test_require_admin_success_super_admin(self):
        """Test successful admin requirement (super admin user)"""
        mock_user = Mock(spec=User)
        mock_user.is_admin.return_value = False
        mock_user.is_super_admin.return_value = True
        
        result = require_admin(mock_user)
        
        assert result == mock_user

    def test_require_admin_failure(self):
        """Test admin requirement failure"""
        mock_user = Mock(spec=User)
        mock_user.is_admin.return_value = False
        mock_user.is_super_admin.return_value = False
        
        with pytest.raises(AuthorizationError, match="Admin access required"):
            require_admin(mock_user)

    def test_require_super_admin_success(self):
        """Test successful super admin requirement"""
        mock_user = Mock(spec=User)
        mock_user.is_super_admin.return_value = True
        
        result = require_super_admin(mock_user)
        
        assert result == mock_user

    def test_require_super_admin_failure(self):
        """Test super admin requirement failure"""
        mock_user = Mock(spec=User)
        mock_user.is_super_admin.return_value = False
        
        with pytest.raises(AuthorizationError, match="Super admin access required"):
            require_super_admin(mock_user)

    def test_require_student_success(self):
        """Test successful student requirement"""
        mock_user = Mock(spec=User)
        mock_user.is_student.return_value = True
        
        result = require_student(mock_user)
        
        assert result == mock_user

    def test_require_student_failure(self):
        """Test student requirement failure"""
        mock_user = Mock(spec=User)
        mock_user.is_student.return_value = False
        
        with pytest.raises(AuthorizationError, match="Student access required"):
            require_student(mock_user)

    def test_require_professor_success(self):
        """Test successful professor requirement"""
        mock_user = Mock(spec=User)
        mock_user.is_professor.return_value = True
        
        result = require_professor(mock_user)
        
        assert result == mock_user

    def test_require_professor_failure(self):
        """Test professor requirement failure"""
        mock_user = Mock(spec=User)
        mock_user.is_professor.return_value = False
        
        with pytest.raises(AuthorizationError, match="Professor access required"):
            require_professor(mock_user)

    def test_require_college_success(self):
        """Test successful college requirement"""
        mock_user = Mock(spec=User)
        mock_user.is_college.return_value = True
        
        result = require_college(mock_user)
        
        assert result == mock_user

    def test_require_college_failure(self):
        """Test college requirement failure"""
        mock_user = Mock(spec=User)
        mock_user.is_college.return_value = False
        
        with pytest.raises(AuthorizationError, match="College access required"):
            require_college(mock_user)

    def test_require_staff_success_admin(self):
        """Test successful staff requirement (admin)"""
        mock_user = Mock(spec=User)
        mock_user.is_admin.return_value = True
        mock_user.is_college.return_value = False
        mock_user.is_professor.return_value = False
        mock_user.is_super_admin.return_value = False
        
        result = require_staff(mock_user)
        
        assert result == mock_user

    def test_require_staff_success_college(self):
        """Test successful staff requirement (college)"""
        mock_user = Mock(spec=User)
        mock_user.is_admin.return_value = False
        mock_user.is_college.return_value = True
        mock_user.is_professor.return_value = False
        mock_user.is_super_admin.return_value = False
        
        result = require_staff(mock_user)
        
        assert result == mock_user

    def test_require_staff_success_professor(self):
        """Test successful staff requirement (professor)"""
        mock_user = Mock(spec=User)
        mock_user.is_admin.return_value = False
        mock_user.is_college.return_value = False
        mock_user.is_professor.return_value = True
        mock_user.is_super_admin.return_value = False
        
        result = require_staff(mock_user)
        
        assert result == mock_user

    def test_require_staff_success_super_admin(self):
        """Test successful staff requirement (super admin)"""
        mock_user = Mock(spec=User)
        mock_user.is_admin.return_value = False
        mock_user.is_college.return_value = False
        mock_user.is_professor.return_value = False
        mock_user.is_super_admin.return_value = True
        
        result = require_staff(mock_user)
        
        assert result == mock_user

    def test_require_staff_failure(self):
        """Test staff requirement failure"""
        mock_user = Mock(spec=User)
        mock_user.is_admin.return_value = False
        mock_user.is_college.return_value = False
        mock_user.is_professor.return_value = False
        mock_user.is_super_admin.return_value = False
        
        with pytest.raises(AuthorizationError, match="Staff access required"):
            require_staff(mock_user)