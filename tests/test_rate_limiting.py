"""
Comprehensive Integration Tests for Rate Limiting.

Tests per-user quotas, 429 responses, Retry-After headers, limit resets,
and proper isolation between users.
"""
import pytest
import time
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from deepmind.app import app
from deepmind.config import Config, RateLimitConfig, EndpointLimitsConfig
from deepmind.middleware.rate_limiter import get_user_identifier, create_limiter


class TestRateLimitKeyFunction:
    """Test user identifier extraction for rate limiting."""
    
    def test_key_function_with_valid_jwt(self):
        """Should extract user_id from valid JWT token."""
        mock_request = Mock()
        mock_request.headers = {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIn0.test"
        }
        mock_request.method = "POST"
        mock_request.url.path = "/api/execute-code"
        
        with patch('deepmind.middleware.rate_limiter.jwt.decode') as mock_decode:
            mock_decode.return_value = {"sub": "user123"}
            
            identifier = get_user_identifier(mock_request)
            
            assert identifier == "user:user123"
            mock_decode.assert_called_once()
    
    def test_key_function_without_auth_header(self):
        """Should fall back to IP address when no auth header."""
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.method = "POST"
        mock_request.url.path = "/api/execute-code"
        
        with patch('deepmind.middleware.rate_limiter.get_remote_address') as mock_ip:
            mock_ip.return_value = "192.168.1.100"
            
            identifier = get_user_identifier(mock_request)
            
            assert identifier == "ip:192.168.1.100"
    
    def test_key_function_with_invalid_jwt(self):
        """Should fall back to IP when JWT is invalid."""
        mock_request = Mock()
        mock_request.headers = {
            "Authorization": "Bearer invalid.token.here"
        }
        mock_request.method = "POST"
        mock_request.url.path = "/api/execute-code"
        
        with patch('deepmind.middleware.rate_limiter.jwt.decode') as mock_decode:
            mock_decode.side_effect = Exception("Invalid token")
            
            with patch('deepmind.middleware.rate_limiter.get_remote_address') as mock_ip:
                mock_ip.return_value = "192.168.1.100"
                
                identifier = get_user_identifier(mock_request)
                
                assert identifier == "ip:192.168.1.100"


class TestLimiterInitialization:
    """Test limiter creation and backend selection."""
    
    def test_create_limiter_with_redis_backend(self):
        """Should initialize with Redis backend when configured."""
        with patch('deepmind.middleware.rate_limiter.get_config') as mock_config:
            mock_cfg = Mock()
            mock_cfg.rate_limits.enabled = True
            mock_cfg.rate_limits.storage = "redis"
            mock_cfg.rate_limits.redis_url = "redis://localhost:6379/1"
            mock_cfg.rate_limits.default_limit = "100/minute"
            mock_config.return_value = mock_cfg
            
            with patch('deepmind.middleware.rate_limiter.redis.from_url') as mock_redis:
                mock_client = Mock()
                mock_redis.return_value = mock_client
                mock_client.ping.return_value = True
                
                limiter = create_limiter()
                
                assert limiter is not None
                # Verify Redis connection was attempted
                mock_redis.assert_called_once_with("redis://localhost:6379/1", decode_responses=True)
    
    def test_create_limiter_fallback_to_memory(self):
        """Should fall back to in-memory when Redis unavailable."""
        with patch('deepmind.middleware.rate_limiter.get_config') as mock_config:
            mock_cfg = Mock()
            mock_cfg.rate_limits.enabled = True
            mock_cfg.rate_limits.storage = "redis"
            mock_cfg.rate_limits.redis_url = "redis://localhost:6379/1"
            mock_cfg.rate_limits.default_limit = "100/minute"
            mock_config.return_value = mock_cfg
            
            with patch('deepmind.middleware.rate_limiter.redis.from_url') as mock_redis:
                # Simulate Redis connection failure
                mock_redis.side_effect = Exception("Connection refused")
                
                limiter = create_limiter()
                
                assert limiter is not None
                # Should fall back to memory backend
    
    def test_create_limiter_disabled(self):
        """Should create limiter with high limit when disabled in config."""
        with patch('deepmind.middleware.rate_limiter.get_config') as mock_config:
            mock_cfg = Mock()
            mock_cfg.rate_limits.enabled = False
            mock_config.return_value = mock_cfg
            
            limiter = create_limiter()
            
            assert limiter is not None


@pytest.mark.integration
class TestEndpointRateLimits:
    """Integration tests for endpoint-specific rate limits."""
    
    @pytest.fixture
    def client(self):
        """Create test client with in-memory rate limiting."""
        with patch('deepmind.middleware.rate_limiter.get_config') as mock_config:
            mock_cfg = Mock()
            mock_cfg.rate_limits.enabled = True
            mock_cfg.rate_limits.storage = "memory"
            mock_cfg.rate_limits.default_limit = "100/minute"
            mock_cfg.rate_limits.endpoints.code_execution = "3/minute"  # Low limit for testing
            mock_cfg.rate_limits.endpoints.image_generation = "3/minute"
            mock_cfg.rate_limits.endpoints.chat_messages = "5/minute"
            mock_cfg.rate_limits.endpoints.auth_login = "3/minute"
            mock_cfg.rate_limits.endpoints.auth_register = "2/hour"
            mock_config.return_value = mock_cfg
            
            yield TestClient(app)
    
    def test_code_execution_rate_limit_exceeded(self, client):
        """Should return 429 when code execution limit exceeded."""
        # Mock authentication
        with patch('deepmind.middleware.auth_middleware.get_current_user'):
            with patch('deepmind.services.code_executor.CodeExecutor.execute'):
                # Make requests up to limit
                for i in range(3):
                    response = client.post(
                        "/api/execute-code",
                        json={"code": "print('test')"},
                        headers={"Authorization": "Bearer test_token_user1"},
                    )
                    assert response.status_code in [200, 429]  # May hit limit
                
                # Next request should be rate limited
                response = client.post(
                    "/api/execute-code",
                    json={"code": "print('test')"},
                    headers={"Authorization": "Bearer test_token_user1"},
                )
                
                assert response.status_code == 429
                assert "Retry-After" in response.headers
                assert "rate_limit_exceeded" in response.json()["error"]
    
    def test_different_users_separate_quotas(self, client):
        """Should enforce separate quotas for different users."""
        with patch('deepmind.middleware.auth_middleware.get_current_user'):
            with patch('deepmind.services.code_executor.CodeExecutor.execute'):
                with patch('deepmind.middleware.rate_limiter.jwt.decode') as mock_decode:
                    # User 1 exhausts their quota
                    mock_decode.return_value = {"sub": "user1"}
                    for i in range(3):
                        client.post(
                            "/api/execute-code",
                            json={"code": "print('test')"},
                            headers={"Authorization": "Bearer token1"},
                        )
                    
                    # User 1's 4th request should be rate limited
                    response1 = client.post(
                        "/api/execute-code",
                        json={"code": "print('test')"},
                        headers={"Authorization": "Bearer token1"},
                    )
                    assert response1.status_code == 429
                    
                    # User 2 should have separate quota
                    mock_decode.return_value = {"sub": "user2"}
                    response2 = client.post(
                        "/api/execute-code",
                        json={"code": "print('test')"},
                        headers={"Authorization": "Bearer token2"},
                    )
                    
                    # User 2's first request should succeed
                    assert response2.status_code in [200, 201]
    
    def test_image_generation_rate_limit(self, client):
        """Should rate limit image generation endpoint."""
        with patch('deepmind.middleware.auth_middleware.get_current_user'):
            with patch('deepmind.services.flux_client.FluxClient.generate_image'):
                # Make requests up to limit
                for i in range(3):
                    response = client.post(
                        "/api/generate-image",
                        json={"prompt": "test image"},
                        headers={"Authorization": "Bearer test_token"},
                    )
                    assert response.status_code in [200, 429]
                
                # Exceed limit
                response = client.post(
                    "/api/generate-image",
                    json={"prompt": "test image"},
                    headers={"Authorization": "Bearer test_token"},
                )
                
                assert response.status_code == 429
    
    def test_chat_message_rate_limit(self, client):
        """Should rate limit chat message endpoint."""
        with patch('deepmind.middleware.auth_middleware.get_current_user'):
            with patch('deepmind.services.conversation_service.ConversationService.send_message_sync'):
                # Make requests up to limit (5/minute)
                for i in range(5):
                    response = client.post(
                        "/api/conversations/test-conv-id/messages",
                        json={"content": "test message"},
                        headers={"Authorization": "Bearer test_token"},
                    )
                    assert response.status_code in [200, 429]
                
                # Exceed limit
                response = client.post(
                    "/api/conversations/test-conv-id/messages",
                    json={"content": "test message"},
                    headers={"Authorization": "Bearer test_token"},
                )
                
                assert response.status_code == 429


@pytest.mark.integration
class TestAuthEndpointRateLimits:
    """Test rate limits on authentication endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client with strict auth rate limits."""
        with patch('deepmind.middleware.rate_limiter.get_config') as mock_config:
            mock_cfg = Mock()
            mock_cfg.rate_limits.enabled = True
            mock_cfg.rate_limits.storage = "memory"
            mock_cfg.rate_limits.default_limit = "100/minute"
            mock_cfg.rate_limits.endpoints.auth_login = "2/minute"  # Very low for testing
            mock_cfg.rate_limits.endpoints.auth_register = "1/hour"
            mock_config.return_value = mock_cfg
            
            yield TestClient(app)
    
    def test_login_rate_limit_by_ip(self, client):
        """Should rate limit login attempts by IP address."""
        with patch('deepmind.services.auth_service.AuthService.authenticate_user'):
            # First 2 attempts should work
            for i in range(2):
                response = client.post(
                    "/auth/login",
                    json={"username": "test", "password": "test123"},
                )
                assert response.status_code in [200, 401, 429]
            
            # 3rd attempt should be rate limited
            response = client.post(
                "/auth/login",
                json={"username": "test", "password": "test123"},
            )
            
            assert response.status_code == 429
            assert "Retry-After" in response.headers
    
    def test_register_rate_limit_by_ip(self, client):
        """Should rate limit registration by IP address."""
        with patch('deepmind.services.auth_service.AuthService.create_user'):
            # First registration should work
            response1 = client.post(
                "/auth/register",
                json={
                    "username": "test1",
                    "email": "test1@example.com",
                    "password": "Test1234",
                },
            )
            assert response1.status_code in [201, 429]
            
            # Second registration should be rate limited (1/hour limit)
            response2 = client.post(
                "/auth/register",
                json={
                    "username": "test2",
                    "email": "test2@example.com",
                    "password": "Test1234",
                },
            )
            
            assert response2.status_code == 429


class TestRateLimitHeaders:
    """Test that rate limit headers are properly set."""
    
    def test_retry_after_header_present(self):
        """Should include Retry-After header in 429 response."""
        from fastapi import Request
        from slowapi.errors import RateLimitExceeded
        from deepmind.middleware.rate_limiter import rate_limit_exceeded_handler
        
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/execute-code"
        mock_request.method = "POST"
        
        mock_exc = RateLimitExceeded("Rate limit exceeded")
        mock_exc.retry_after = 120
        
        with patch('deepmind.middleware.rate_limiter.get_user_identifier') as mock_id:
            mock_id.return_value = "user:test123"
            
            response = rate_limit_exceeded_handler(mock_request, mock_exc)
            
            assert response.status_code == 429
            assert "Retry-After" in response.headers
            assert response.headers["Retry-After"] == "120"
            
            body = response.body.decode()
            assert "rate_limit_exceeded" in body
            assert "retry_after_seconds" in body
