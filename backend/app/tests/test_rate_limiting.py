"""
Unit tests for rate limiting functionality
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from app.core.rate_limiting import RateLimiter, professor_rate_limit, rate_limit


class TestRateLimiter:
    """Test core RateLimiter class"""

    @pytest.fixture
    async def mock_redis(self):
        """Mock Redis connection"""
        mock_redis = AsyncMock()
        mock_redis.pipeline.return_value.__aenter__.return_value.execute.return_value = [
            None,  # zremrangebyscore result
            0,  # zcard result (current request count)
            None,  # zadd result
            None,  # expire result
        ]
        return mock_redis

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        """RateLimiter instance with mocked Redis"""
        limiter = RateLimiter("redis://localhost:6379")
        limiter.redis = mock_redis
        return limiter

    @pytest.mark.asyncio
    async def test_is_rate_limited_under_limit(self, rate_limiter, mock_redis):
        """Test rate limiting when under the limit"""
        # Mock pipeline execution to return 0 current requests
        pipeline_mock = AsyncMock()
        pipeline_mock.execute.return_value = [None, 0, None, None]
        mock_redis.pipeline.return_value.__aenter__.return_value = pipeline_mock

        is_limited, remaining = await rate_limiter.is_rate_limited("test_key", 10, 3600)

        assert is_limited is False
        assert remaining == 9  # 10 limit - 0 current - 1 for this request

    @pytest.mark.asyncio
    async def test_is_rate_limited_at_limit(self, rate_limiter, mock_redis):
        """Test rate limiting when at the limit"""
        # Mock pipeline execution to return limit number of requests
        pipeline_mock = AsyncMock()
        pipeline_mock.execute.return_value = [None, 10, None, None]  # Already at limit
        mock_redis.pipeline.return_value.__aenter__.return_value = pipeline_mock

        is_limited, remaining = await rate_limiter.is_rate_limited("test_key", 10, 3600)

        assert is_limited is True
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_is_rate_limited_redis_error_fails_open(self, rate_limiter, mock_redis):
        """Test that Redis errors fail open (don't block requests)"""
        # Mock Redis to raise an exception
        mock_redis.pipeline.side_effect = Exception("Redis connection failed")

        is_limited, remaining = await rate_limiter.is_rate_limited("test_key", 10, 3600)

        assert is_limited is False
        assert remaining == 10  # Should return limit as remaining when failing open


class TestRateLimitDecorator:
    """Test rate limiting decorator functionality"""

    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI request"""
        request = Mock()
        request.client.host = "127.0.0.1"
        request.method = "GET"
        request.url = "http://test.com/api/endpoint"
        return request

    @pytest.fixture
    def mock_user(self):
        """Mock user object"""
        user = Mock()
        user.id = 123
        user.role = "professor"
        return user

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_success(self, mock_request, mock_user):
        """Test rate limit decorator when request is allowed"""
        # Mock the rate limiter to allow request
        with patch("app.core.rate_limiting.get_rate_limiter") as mock_get_limiter:
            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 5))
            mock_get_limiter.return_value = mock_limiter

            @rate_limit(requests=10, window_seconds=60)
            async def test_endpoint(request, current_user):
                return {"success": True, "data": "test"}

            result = await test_endpoint(mock_request, mock_user)

            assert result == {"success": True, "data": "test"}
            mock_limiter.is_rate_limited.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_blocked(self, mock_request, mock_user):
        """Test rate limit decorator when request is blocked"""
        with patch("app.core.rate_limiting.get_rate_limiter") as mock_get_limiter:
            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(True, 0))
            mock_get_limiter.return_value = mock_limiter

            @rate_limit(requests=10, window_seconds=60)
            async def test_endpoint(request, current_user):
                return {"success": True, "data": "test"}

            with pytest.raises(HTTPException) as exc_info:
                await test_endpoint(mock_request, mock_user)

            assert exc_info.value.status_code == 429
            assert "Rate limit exceeded" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_professor_rate_limit_key_generation(self, mock_request, mock_user):
        """Test that professor rate limit generates correct key"""
        with patch("app.core.rate_limiting.get_rate_limiter") as mock_get_limiter:
            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 5))
            mock_get_limiter.return_value = mock_limiter

            @professor_rate_limit(requests=30, window_seconds=600)
            async def test_professor_endpoint(request, current_user):
                return {"success": True}

            await test_professor_endpoint(mock_request, mock_user)

            # Check that the rate limiter was called with the expected key format
            call_args = mock_limiter.is_rate_limited.call_args
            key_used = call_args[0][0]  # First positional argument is the key

            assert "professor_api:user:123" == key_used
            assert call_args[0][1] == 30  # requests limit
            assert call_args[0][2] == 600  # window seconds

    @pytest.mark.asyncio
    async def test_rate_limit_with_ip_fallback(self, mock_request):
        """Test rate limiting falls back to IP when no user provided"""
        with patch("app.core.rate_limiting.get_rate_limiter") as mock_get_limiter:
            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 5))
            mock_get_limiter.return_value = mock_limiter

            @rate_limit(requests=10, window_seconds=60)
            async def test_endpoint(request):
                return {"success": True}

            await test_endpoint(mock_request)

            # Check that IP-based key was generated
            call_args = mock_limiter.is_rate_limited.call_args
            key_used = call_args[0][0]

            assert "rate_limit:ip:127.0.0.1:test_endpoint" == key_used

    @pytest.mark.asyncio
    async def test_rate_limit_custom_key_function(self, mock_request, mock_user):
        """Test rate limiting with custom key function"""

        def custom_key_func(request, current_user):
            return f"custom:key:{current_user.id if current_user else 'anon'}"

        with patch("app.core.rate_limiting.get_rate_limiter") as mock_get_limiter:
            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 5))
            mock_get_limiter.return_value = mock_limiter

            @rate_limit(requests=10, window_seconds=60, key_func=custom_key_func)
            async def test_endpoint(request, current_user):
                return {"success": True}

            await test_endpoint(mock_request, mock_user)

            call_args = mock_limiter.is_rate_limited.call_args
            key_used = call_args[0][0]

            assert key_used == "custom:key:123"


class TestRateLimitIntegration:
    """Integration tests for rate limiting with actual Redis (if available)"""

    @pytest.fixture
    def redis_available(self):
        """Check if Redis is available for testing"""
        try:
            import redis

            r = redis.Redis(host="localhost", port=6379, db=0)
            r.ping()
            return True
        except Exception:
            return False

    @pytest.mark.asyncio
    @pytest.mark.skipif(True, reason="Requires Redis server - enable for integration testing")
    async def test_real_redis_rate_limiting(self, redis_available):
        """Integration test with real Redis (skipped by default)"""
        if not redis_available:
            pytest.skip("Redis not available")

        limiter = RateLimiter("redis://localhost:6379")

        # Test multiple requests within limit
        for i in range(5):
            is_limited, remaining = await limiter.is_rate_limited("test_integration", 10, 60)
            assert is_limited is False
            assert remaining >= 0

        # Test exceeding limit
        for i in range(10):  # This should exceed the limit
            is_limited, remaining = await limiter.is_rate_limited("test_integration_limit", 3, 60)
            if i >= 3:
                assert is_limited is True

        await limiter.close()


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
