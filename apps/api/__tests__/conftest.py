"""
Pytest configuration and fixtures for API tests.

Uses mocks for:
- Authentication (JWT/API Key) - via FastAPI dependency overrides
- Database session - via mock AsyncSession
"""
import os
import sys
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Add the app directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
# from shared.models.database.user import User
from shared.core.database import get_db
from app.core.dependencies import get_current_user_id


# =============================================================================
# Mock User Factory
# =============================================================================

def create_mock_user(
    user_id: str = None,
    email: str = "test@example.com",
    username: str = "testuser"
):
    """Create a mock User ID for testing."""
    return user_id or str(uuid4())


# =============================================================================
# Mock Database Session
# =============================================================================

@pytest_asyncio.fixture
async def mock_db() -> AsyncMock:
    """Create a mock AsyncSession for database operations."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.get = AsyncMock()
    return mock_session


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_user_id() -> str:
    """Create a mock authenticated user ID."""
    return create_mock_user()


@pytest_asyncio.fixture
async def authenticated_client(mock_user_id: str, mock_db: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an async test client with mocked authentication.
    
    This overrides the FastAPI dependencies to:
    - Return a mock user ID for all auth-protected endpoints
    - Use a mock database session
    """
    # Override auth dependency to return mock user ID
    async def mock_get_current_user_id():
        return mock_user_id
    
    # Override database dependency to return mock session
    async def mock_get_db():
        yield mock_db
    
    # Apply dependency overrides
    app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
    app.dependency_overrides[get_db] = mock_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    # Clear overrides after test
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Create an async test client WITHOUT mocked auth.
    Used for testing unauthenticated requests.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_job_id() -> str:
    """Generate a unique test job ID."""
    return f"job_{uuid4().hex[:12]}"
