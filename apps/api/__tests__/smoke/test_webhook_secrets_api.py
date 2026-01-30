"""
Smoke tests for Webhook Secrets API.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime

from shared.models.database.webhook_secret import WebhookSecret, WebhookSecretStatus


from main import app
from app.core.dependencies import get_current_user
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def mock_secret():
    """Create a mock WebhookSecret object."""
    secret = MagicMock(spec=WebhookSecret)
    secret.id = f"ws_{uuid4().hex[:24]}"
    secret.user_id = str(uuid4())
    secret.endpoint = "https://example.com/webhook"
    secret.secret_encrypted = "encrypted_value"
    secret.status = WebhookSecretStatus.ACTIVE
    secret.created_at = datetime.utcnow()
    secret._raw_secret = "whsec_test123" # Mock decrypted value
    return secret


@pytest.fixture
async def authenticated_client(mock_user, mock_db):
    """
    Local authenticated client that overrides get_current_user.
    """
    async def mock_get_current_user():
        return mock_user
        
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_secrets(authenticated_client, mock_secret):
    """Test standard list secrets endpoint."""
    with patch("app.api.v1.routes.webhook_secrets.WebhookSecretRepository") as MockRepo:
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.list_secrets = AsyncMock(return_value=[mock_secret])
        
        response = await authenticated_client.get("/v1/webhooks/secrets")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["secrets"][0]["id"] == mock_secret.id
        assert data["secrets"][0]["status"] == "active"
        # Secrets should be masked in list view (secret field should NOT exist)
        assert "secret" not in data["secrets"][0]
        assert "****" in data["secrets"][0]["secret_masked"]


@pytest.mark.asyncio
async def test_create_secret_new(authenticated_client, mock_secret):
    """Test creating a new secret."""
    with patch("app.api.v1.routes.webhook_secrets.WebhookSecretRepository") as MockRepo:
        mock_repo_instance = MockRepo.return_value
        # Mock no existing secret
        mock_repo_instance.get_active_secret = AsyncMock(return_value=None)
        mock_repo_instance.create_secret = AsyncMock(return_value=mock_secret)
        
        payload = {"endpoint": "https://example.com/webhook"}
        response = await authenticated_client.post("/v1/webhooks/secrets", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == mock_secret.id
        # Newly created secret should return the raw value
        assert data["secret"] == "whsec_test123"


@pytest.mark.asyncio
async def test_create_secret_existing(authenticated_client, mock_secret):
    """Test creating secret returns existing if active."""
    with patch("app.api.v1.routes.webhook_secrets.WebhookSecretRepository") as MockRepo:
        mock_repo_instance = MockRepo.return_value
        # Mock existing active secret
        mock_repo_instance.get_active_secret = AsyncMock(return_value=mock_secret)
        
        payload = {"endpoint": "https://example.com/webhook"}
        response = await authenticated_client.post("/v1/webhooks/secrets", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == mock_secret.id
        # Existing secret should NOT return raw value (security)
        assert "secret" not in data


@pytest.mark.asyncio
async def test_revoke_secret(authenticated_client):
    """Test revoking a secret."""
    secret_id = "ws_test123"
    with patch("app.api.v1.routes.webhook_secrets.WebhookSecretRepository") as MockRepo:
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.revoke_secret = AsyncMock(return_value=True)
        
        response = await authenticated_client.delete(f"/v1/webhooks/secrets/{secret_id}")
        
        assert response.status_code == 200
        assert response.json()["id"] == secret_id
        assert response.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_revoke_secret_not_found(authenticated_client):
    """Test revoking non-existent secret returns 404."""
    secret_id = "ws_test123"
    with patch("app.api.v1.routes.webhook_secrets.WebhookSecretRepository") as MockRepo:
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.revoke_secret = AsyncMock(return_value=False)
        
        response = await authenticated_client.delete(f"/v1/webhooks/secrets/{secret_id}")
        
        assert response.status_code == 404
