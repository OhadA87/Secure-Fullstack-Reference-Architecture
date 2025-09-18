import pytest
from unittest.mock import patch
import time
from httpx import AsyncClient
from fastapi.testclient import TestClient

from apps.api_fastapi.app.main import app
from apps.api_fastapi.app.security.jwt import jwt_manager, TokenData


class TestAuth:
    """Comprehensive auth testing suite."""
    
    @pytest.fixture
    def client(self):
        """Test client fixture."""
        return TestClient(app)
    
    @pytest.fixture
    async def async_client(self):
        """Async test client fixture."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    
    @pytest.fixture
    def mock_valid_user_token(self):
        """Generate a valid user token for testing."""
        return jwt_manager.create_access_token(
            user_id="user_123",
            email="demo@example.com", 
            roles=["user"]
        )
    
    @pytest.fixture
    def mock_admin_token(self):
        """Generate a valid admin token for testing."""
        return jwt_manager.create_access_token(
            user_id="admin_456",
            email="admin@example.com",
            roles=["admin", "user"]
        )
    
    @pytest.fixture
    def mock_refresh_token(self):
        """Generate a valid refresh token for testing."""
        return jwt_manager.create_refresh_token(
            user_id="user_123",
            email="demo@example.com"
        )

    # Login Tests
    async def test_login_success_user(self, async_client: AsyncClient):
        """Test successful login with valid user credentials."""
        response = await async_client.post(
            "/auth/login",
            json={"email": "demo@example.com", "password": "demo"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        
        # Verify access token is valid JWT
        token_data = jwt_manager.decode_token(data["access_token"])
        assert token_data is not None
        assert token_data.email == "demo@example.com"
        assert token_data.user_id == "user_123"
        assert "user" in token_data.roles
        assert token_data.token_type == "access"
    
    async def test_login_success_admin(self, async_client: AsyncClient):
        """Test successful login with admin credentials."""
        response = await async_client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "admin"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify admin token has correct roles
        token_data = jwt_manager.decode_token(data["access_token"])
        assert token_data is not None
        assert "admin" in token_data.roles
        assert "user" in token_data.roles
    
    async def test_login_invalid_email(self, async_client: AsyncClient):
        """Test login with non-existent email."""
        response = await async_client.post(
            "/auth/login",
            json={"email": "nonexistent@example.com", "password": "password"}
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"
    
    async def test_login_invalid_password(self, async_client: AsyncClient):
        """Test login with wrong password."""
        response = await async_client.post(
            "/auth/login",
            json={"email": "demo@example.com", "password": "wrongpassword"}
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"
    
    async def test_login_missing_fields(self, async_client: AsyncClient):
        """Test login with missing required fields."""
        # Missing password
        response = await async_client.post(
            "/auth/login",
            json={"email": "demo@example.com"}
        )
        assert response.status_code == 422
        
        # Missing email
        response = await async_client.post(
            "/auth/login",
            json={"password": "demo"}
        )
        assert response.status_code == 422
    
    # Rate Limiting Tests
    async def test_login_rate_limit(self, async_client: AsyncClient):
        """Test rate limiting on login endpoint."""
        # Make multiple rapid requests to trigger rate limit
        for i in range(12):  # Limit is 10/minute
            response = await async_client.post(
                "/auth/login",
                json={"email": "demo@example.com", "password": "demo"}
            )
            if i < 10:
                assert response.status_code == 200
            else:
                # Should be rate limited after 10 requests
                assert response.status_code == 429
    
    # Token Refresh Tests
    async def test_refresh_token_success(self, async_client: AsyncClient, mock_refresh_token):
        """Test successful token refresh."""
        response = await async_client.post(
            "/auth/refresh",
            json={"refresh_token": mock_refresh_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    async def test_refresh_token_invalid(self, async_client: AsyncClient):
        """Test refresh with invalid token."""
        response = await async_client.post(
            "/auth/refresh",
            json={"refresh_token": "invalid_token"}
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid refresh token"
    
    async def test_refresh_token_access_token_used(self, async_client: AsyncClient, mock_valid_user_token):
        """Test refresh endpoint rejects access tokens."""
        response = await async_client.post(
            "/auth/refresh",
            json={"refresh_token": mock_valid_user_token}  # Using access token instead of refresh
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid refresh token"
    
    # RBAC Tests
    async def test_user_endpoint_with_valid_token(self, async_client: AsyncClient, mock_valid_user_token):
        """Test user endpoint access with valid user token."""
        response = await async_client.get(
            "/protected/user",
            headers={"Authorization": f"Bearer {mock_valid_user_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "User access granted"
        assert data["user_id"] == "user_123"
        assert data["email"] == "demo@example.com"
        assert "user" in data["roles"]
    
    async def test_admin_endpoint_with_admin_token(self, async_client: AsyncClient, mock_admin_token):
        """Test admin endpoint access with admin token."""
        response = await async_client.get(
            "/protected/admin",
            headers={"Authorization": f"Bearer {mock_admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Admin access granted"
        assert data["user_id"] == "admin_456"
    
    async def test_admin_endpoint_rbac_denial(self, async_client: AsyncClient, mock_valid_user_token):
        """Test RBAC denial when user tries to access admin endpoint."""
        response = await async_client.get(
            "/protected/admin",
            headers={"Authorization": f"Bearer {mock_valid_user_token}"}
        )
        
        assert response.status_code == 403
        assert response.json()["detail"] == "Insufficient permissions"
    
    async def test_protected_endpoint_no_token(self, async_client: AsyncClient):
        """Test protected endpoint access without token."""
        response = await async_client.get("/protected/user")
        
        assert response.status_code == 401
        assert "Missing authentication token" in response.json()["detail"]
    
    async def test_protected_endpoint_invalid_token(self, async_client: AsyncClient):
        """Test protected endpoint access with invalid token."""
        response = await async_client.get(
            "/protected/user",
            headers={"Authorization": "Bearer invalid_token"}
        )
        
        assert response.status_code == 401
        assert "Invalid authentication token" in response.json()["detail"]
    
    async def test_protected_endpoint_malformed_header(self, async_client: AsyncClient):
        """Test protected endpoint with malformed auth header."""
        # Missing Bearer prefix
        response = await async_client.get(
            "/protected/user",
            headers={"Authorization": "invalid_format_token"}
        )
        
        assert response.status_code == 401
    
    async def test_protected_endpoint_expired_token(self, async_client: AsyncClient):
        """Test protected endpoint with expired token."""
        # Create token that's already expired
        with patch('apps.api_fastapi.app.security.jwt.datetime') as mock_datetime:
            # Mock datetime to create expired token
            past_time = time.time() - 3600  # 1 hour ago
            mock_datetime.now.return_value.timestamp.return_value = past_time
            
            expired_token = jwt_manager.create_access_token(
                user_id="user_123",
                email="demo@example.com",
                roles=["user"]
            )
        
        response = await async_client.get(
            "/protected/user",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        
        assert response.status_code == 401
    
    # Health Endpoint Test
    async def test_health_endpoint(self, async_client: AsyncClient):
        """Test health endpoint (no auth required)."""
        response = await async_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "api"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data
    
    # Metrics Endpoint Test
    async def test_metrics_endpoint(self, async_client: AsyncClient):
        """Test Prometheus metrics endpoint (no auth required)."""
        response = await async_client.get("/metrics")
        
        assert response.status_code == 200
        # Should contain Prometheus metrics format
        content = response.content.decode()
        assert "http_requests_total" in content
        assert "http_request_duration_seconds" in content


@pytest.mark.asyncio
class TestJWTManager:
    """Test JWT manager functionality in isolation."""
    
    def test_create_access_token(self):
        """Test access token creation."""
        token = jwt_manager.create_access_token(
            user_id="test_user",
            email="test@example.com",
            roles=["user"]
        )
        
        token_data = jwt_manager.decode_token(token)
        assert token_data is not None
        assert token_data.user_id == "test_user"
        assert token_data.email == "test@example.com"
        assert token_data.roles == ["user"]
        assert token_data.token_type == "access"
    
    def test_create_refresh_token(self):
        """Test refresh token creation."""
        token = jwt_manager.create_refresh_token(
            user_id="test_user",
            email="test@example.com"
        )
        
        token_data = jwt_manager.decode_token(token)
        assert token_data is not None
        assert token_data.user_id == "test_user"
        assert token_data.email == "test@example.com"
        assert token_data.token_type == "refresh"
        assert token_data.roles == []  # Refresh tokens don't have roles
    
    def test_decode_invalid_token(self):
        """Test decoding invalid token."""
        result = jwt_manager.decode_token("invalid.token.here")
        assert result is None
    
    def test_extract_token_from_header(self):
        """Test token extraction from Authorization header."""
        # Valid header
        token = jwt_manager.extract_token_from_header("Bearer valid_token_here")
        assert token == "valid_token_here"
        
        # Invalid scheme
        token = jwt_manager.extract_token_from_header("Basic valid_token_here")
        assert token is None
        
        # Malformed header
        token = jwt_manager.extract_token_from_header("Bearer")
        assert token is None
        
        # Empty header
        token = jwt_manager.extract_token_from_header("")
        assert token is None