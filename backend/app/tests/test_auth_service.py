"""
Unit tests for AuthService
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import AuthService
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserLogin, TokenResponse, UserResponse
from app.core.exceptions import AuthenticationError, ConflictError


class TestAuthService:
    """Test cases for AuthService"""

    @pytest.fixture
    def service(self, db: AsyncSession):
        """Create AuthService instance for testing"""
        return AuthService(db)

    @pytest.fixture
    def mock_user_create_data(self):
        """Mock user creation data"""
        return UserCreate(
            nycu_id="112550001",
            name="Test User",
            email="test@nycu.edu.tw",
            user_type="student",
            status="active",
            dept_code="CS",
            dept_name="Computer Science",
            role=UserRole.STUDENT
        )

    @pytest.fixture
    def mock_user_login_data(self):
        """Mock user login data"""
        return UserLogin(
            username="112550001",
            password="testpassword123"
        )

    @pytest.fixture
    def mock_user(self):
        """Mock user object"""
        user = Mock(spec=User)
        user.id = 1
        user.nycu_id = "112550001"
        user.name = "Test User"
        user.email = "test@nycu.edu.tw"
        user.role = UserRole.STUDENT
        user.user_type = "student"
        user.status = "active"
        user.dept_code = "CS"
        user.dept_name = "Computer Science"
        user.last_login_at = None
        return user

    @pytest.mark.asyncio
    async def test_register_user_success(self, service, mock_user_create_data):
        """Test successful user registration"""
        with patch.object(service.db, 'execute') as mock_execute, \
             patch.object(service.db, 'add') as mock_add, \
             patch.object(service.db, 'commit') as mock_commit, \
             patch.object(service.db, 'refresh') as mock_refresh:
            
            # Mock no existing users with same email or nycu_id
            mock_execute.return_value.scalar_one_or_none.return_value = None
            
            # Mock user creation
            mock_user = Mock(spec=User)
            mock_user.id = 1
            mock_user.nycu_id = mock_user_create_data.nycu_id
            mock_user.name = mock_user_create_data.name
            mock_user.email = mock_user_create_data.email
            mock_user.role = mock_user_create_data.role
            
            with patch('app.schemas.user.UserResponse.model_validate') as mock_validate:
                mock_response = UserResponse(
                    id=1,
                    nycu_id=mock_user_create_data.nycu_id,
                    name=mock_user_create_data.name,
                    email=mock_user_create_data.email,
                    role=mock_user_create_data.role,
                    user_type=mock_user_create_data.user_type,
                    status=mock_user_create_data.status
                )
                mock_validate.return_value = mock_response
                
                result = await service.register_user(mock_user_create_data)
                
                # Verify database operations
                assert mock_execute.call_count == 2  # Check email and nycu_id
                mock_add.assert_called_once()
                mock_commit.assert_called_once()
                mock_refresh.assert_called_once()
                
                # Verify result
                assert result == mock_response

    @pytest.mark.asyncio
    async def test_register_user_email_exists(self, service, mock_user_create_data):
        """Test user registration when email already exists"""
        existing_user = Mock(spec=User)
        existing_user.email = mock_user_create_data.email
        
        with patch.object(service.db, 'execute') as mock_execute:
            # Mock existing user with same email
            mock_execute.return_value.scalar_one_or_none.return_value = existing_user
            
            with pytest.raises(ConflictError, match="Email already registered"):
                await service.register_user(mock_user_create_data)

    @pytest.mark.asyncio
    async def test_register_user_nycu_id_exists(self, service, mock_user_create_data):
        """Test user registration when NYCU ID already exists"""
        existing_user = Mock(spec=User)
        existing_user.nycu_id = mock_user_create_data.nycu_id
        
        with patch.object(service.db, 'execute') as mock_execute:
            # Mock no user with same email, but user with same nycu_id
            mock_execute.return_value.scalar_one_or_none.side_effect = [None, existing_user]
            
            with pytest.raises(ConflictError, match="NYCU ID already exists"):
                await service.register_user(mock_user_create_data)

    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, service, mock_user_login_data, mock_user):
        """Test successful user authentication"""
        with patch.object(service.db, 'execute') as mock_execute, \
             patch.object(service.db, 'commit') as mock_commit:
            
            mock_execute.return_value.scalar_one_or_none.return_value = mock_user
            
            result = await service.authenticate_user(mock_user_login_data)
            
            # Verify user was found and last_login_at was updated
            assert result == mock_user
            assert mock_user.last_login_at is not None
            mock_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, service, mock_user_login_data):
        """Test user authentication when user not found"""
        with patch.object(service.db, 'execute') as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = None
            
            with pytest.raises(AuthenticationError, match="Invalid nycu_id or email"):
                await service.authenticate_user(mock_user_login_data)

    @pytest.mark.asyncio
    async def test_authenticate_user_by_email(self, service, mock_user):
        """Test user authentication using email instead of nycu_id"""
        login_data = UserLogin(
            username="test@nycu.edu.tw",  # Using email as username
            password="testpassword123"
        )
        
        with patch.object(service.db, 'execute') as mock_execute, \
             patch.object(service.db, 'commit') as mock_commit:
            
            mock_execute.return_value.scalar_one_or_none.return_value = mock_user
            
            result = await service.authenticate_user(login_data)
            
            # Verify user was found
            assert result == mock_user
            mock_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_tokens(self, service, mock_user):
        """Test token creation for authenticated user"""
        with patch('app.services.auth_service.create_access_token') as mock_access_token, \
             patch('app.services.auth_service.create_refresh_token') as mock_refresh_token, \
             patch('app.schemas.user.UserResponse.model_validate') as mock_validate:
            
            # Mock token creation
            mock_access_token.return_value = "mock_access_token"
            mock_refresh_token.return_value = "mock_refresh_token"
            
            # Mock user response
            mock_user_response = UserResponse(
                id=mock_user.id,
                nycu_id=mock_user.nycu_id,
                name=mock_user.name,
                email=mock_user.email,
                role=mock_user.role,
                user_type=mock_user.user_type,
                status=mock_user.status
            )
            mock_validate.return_value = mock_user_response
            
            result = await service.create_tokens(mock_user)
            
            # Verify token data
            expected_token_data = {
                "sub": str(mock_user.id),
                "nycu_id": mock_user.nycu_id,
                "role": mock_user.role.value
            }
            
            mock_access_token.assert_called_once_with(expected_token_data)
            mock_refresh_token.assert_called_once_with(expected_token_data)
            
            # Verify result
            assert isinstance(result, TokenResponse)
            assert result.access_token == "mock_access_token"
            assert result.refresh_token == "mock_refresh_token"
            assert result.expires_in == 3600
            assert result.user == mock_user_response

    @pytest.mark.asyncio
    async def test_login_success(self, service, mock_user_login_data, mock_user):
        """Test complete login flow"""
        with patch.object(service, 'authenticate_user') as mock_auth, \
             patch.object(service, 'create_tokens') as mock_create_tokens:
            
            # Mock authentication and token creation
            mock_auth.return_value = mock_user
            mock_token_response = TokenResponse(
                access_token="mock_access_token",
                refresh_token="mock_refresh_token",
                expires_in=3600,
                user=UserResponse(
                    id=mock_user.id,
                    nycu_id=mock_user.nycu_id,
                    name=mock_user.name,
                    email=mock_user.email,
                    role=mock_user.role,
                    user_type=mock_user.user_type,
                    status=mock_user.status
                )
            )
            mock_create_tokens.return_value = mock_token_response
            
            result = await service.login(mock_user_login_data)
            
            # Verify authentication and token creation were called
            mock_auth.assert_called_once_with(mock_user_login_data)
            mock_create_tokens.assert_called_once_with(mock_user)
            
            # Verify result
            assert result == mock_token_response

    @pytest.mark.asyncio
    async def test_get_user_by_id_success(self, service, mock_user):
        """Test getting user by ID successfully"""
        user_id = 1
        
        with patch.object(service.db, 'get') as mock_get:
            mock_get.return_value = mock_user
            
            result = await service.get_user_by_id(user_id)
            
            mock_get.assert_called_once_with(User, user_id)
            assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, service):
        """Test getting user by ID when user not found"""
        user_id = 999
        
        with patch.object(service.db, 'get') as mock_get:
            mock_get.return_value = None
            
            result = await service.get_user_by_id(user_id)
            
            mock_get.assert_called_once_with(User, user_id)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_nycu_id_success(self, service, mock_user):
        """Test getting user by NYCU ID successfully"""
        nycu_id = "112550001"
        
        with patch.object(service.db, 'execute') as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_user
            
            result = await service.get_user_by_nycu_id(nycu_id)
            
            assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_user_by_nycu_id_not_found(self, service):
        """Test getting user by NYCU ID when user not found"""
        nycu_id = "999999999"
        
        with patch.object(service.db, 'execute') as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = None
            
            result = await service.get_user_by_nycu_id(nycu_id)
            
            assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_email_success(self, service, mock_user):
        """Test getting user by email successfully"""
        email = "test@nycu.edu.tw"
        
        with patch.object(service.db, 'execute') as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_user
            
            result = await service.get_user_by_email(email)
            
            assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_user_by_email_not_found(self, service):
        """Test getting user by email when user not found"""
        email = "nonexistent@nycu.edu.tw"
        
        with patch.object(service.db, 'execute') as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = None
            
            result = await service.get_user_by_email(email)
            
            assert result is None

    @pytest.mark.asyncio
    async def test_create_user_alias(self, service, mock_user_create_data):
        """Test create_user method (alias for register_user)"""
        with patch.object(service, 'register_user') as mock_register:
            mock_response = UserResponse(
                id=1,
                nycu_id=mock_user_create_data.nycu_id,
                name=mock_user_create_data.name,
                email=mock_user_create_data.email,
                role=mock_user_create_data.role,
                user_type=mock_user_create_data.user_type,
                status=mock_user_create_data.status
            )
            mock_register.return_value = mock_response
            
            result = await service.create_user(mock_user_create_data)
            
            mock_register.assert_called_once_with(mock_user_create_data)
            assert result == mock_response

    @pytest.mark.asyncio
    async def test_authenticate_user_updates_last_login(self, service, mock_user_login_data, mock_user):
        """Test that authentication updates the user's last login time"""
        original_last_login = mock_user.last_login_at
        
        with patch.object(service.db, 'execute') as mock_execute, \
             patch.object(service.db, 'commit') as mock_commit:
            
            mock_execute.return_value.scalar_one_or_none.return_value = mock_user
            
            await service.authenticate_user(mock_user_login_data)
            
            # Verify last_login_at was updated
            assert mock_user.last_login_at != original_last_login
            assert isinstance(mock_user.last_login_at, datetime)
            mock_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_data_structure(self, service, mock_user):
        """Test that token data contains expected fields"""
        with patch('app.services.auth_service.create_access_token') as mock_access_token, \
             patch('app.services.auth_service.create_refresh_token') as mock_refresh_token, \
             patch('app.schemas.user.UserResponse.model_validate'):
            
            await service.create_tokens(mock_user)
            
            # Get the token data that was passed to token creation functions
            call_args = mock_access_token.call_args[0][0]
            
            # Verify token data structure
            assert "sub" in call_args
            assert "nycu_id" in call_args
            assert "role" in call_args
            assert call_args["sub"] == str(mock_user.id)
            assert call_args["nycu_id"] == mock_user.nycu_id
            assert call_args["role"] == mock_user.role.value