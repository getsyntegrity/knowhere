"""
API Smoke Tests - Organized by Requirement
Tests verify side effects (DB persistence, MQ publish) without importing Worker code.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4

from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
from shared.tests.fakes import FakeAsyncSession, FakeCeleryApp
from app.services.webhook.webhook_event_service import WebhookEventService
from app.services.webhook.webhook_service import WebhookService

# --- Fixtures ---
@pytest.fixture
def fake_db():
    return FakeAsyncSession()

@pytest.fixture
def fake_celery():
    return FakeCeleryApp()

@pytest.fixture
def event_service():
    return WebhookEventService()

# =============================================================================
# FR-01: Event Trigger
# =============================================================================
@pytest.mark.asyncio
async def test_fr01_event_trigger_creates_pending_event(fake_db, fake_celery, event_service):
    """
    FR-01: When a job completes, a WebhookEvent is created with PENDING status.
    Verify: Event persisted in DB with correct fields.
    """
    job_id = str(uuid4())
    
    with patch("shared.core.celery_app.get_celery_app", return_value=fake_celery):
        event = await event_service.create_and_publish_event(
            db=fake_db,
            job_id=job_id,
            target_url="https://example.com/webhook",
            secret="test_secret",
            payload={"job_id": job_id, "status": "done"}
        )
    
    # Verify DB Side Effect
    assert event in fake_db.storage
    assert event.status == WebhookEventStatus.PENDING
    assert event.job_id == job_id
    assert event.attempts == 0

@pytest.mark.asyncio
async def test_fr01_event_trigger_sends_celery_task(fake_db, fake_celery, event_service):
    """
    FR-01: After event creation, a Celery task is dispatched.
    Verify: Task sent to broker with correct event_id.
    """
    job_id = str(uuid4())
    
    with patch("shared.core.celery_app.get_celery_app", return_value=fake_celery):
        event = await event_service.create_and_publish_event(
            db=fake_db,
            job_id=job_id,
            target_url="https://example.com/webhook",
            secret="test_secret",
            payload={"status": "done"}
        )
    
    # Verify MQ Side Effect
    assert len(fake_celery.tasks) == 1
    task = fake_celery.tasks[0]
    assert task["name"] == "app.core.tasks.webhook_tasks.dispatch_webhook_task"
    assert task["args"][0] == event.id


# =============================================================================
# FR-02: Dynamic Configuration
# =============================================================================
@pytest.mark.asyncio
async def test_fr02_rejects_invalid_url_scheme(fake_db, event_service):
    """
    FR-02: Webhook URL must be http or https.
    Verify: ftp:// URL is rejected.
    """
    from shared.core.exceptions.webhook_exceptions import WebhookConfigException
    
    with pytest.raises(WebhookConfigException) as exc:
        await event_service.create_event(
            db=fake_db,
            job_id=str(uuid4()),
            target_url="ftp://invalid.com/webhook",
            secret="secret",
            payload={}
        )
    assert "http://" in exc.value.user_message or "https://" in exc.value.user_message

@pytest.mark.asyncio
async def test_fr02_rejects_empty_secret(fake_db, event_service):
    """
    FR-02: Webhook secret is required.
    Verify: Empty secret is rejected.
    """
    from shared.core.exceptions.webhook_exceptions import WebhookConfigException
    
    with pytest.raises(WebhookConfigException) as exc:
        await event_service.create_event(
            db=fake_db,
            job_id=str(uuid4()),
            target_url="https://example.com/webhook",
            secret="",
            payload={}
        )
    assert "secret" in exc.value.user_message.lower()


# =============================================================================
# FR-09: Manual Trigger
# =============================================================================
@pytest.mark.asyncio
async def test_fr09_manual_trigger_executes_synchronously():
    """
    FR-09: Manual trigger sends webhook immediately (not via queue).
    Verify: HTTP request is made and result returned directly.
    """
    service = WebhookService()
    job_id = str(uuid4())
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value="OK")
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None
    
    with patch("aiohttp.ClientSession.post", return_value=mock_response), \
         patch("app.services.webhook.webhook_service.get_db_context") as mock_ctx:
        
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.return_value.__aexit__ = AsyncMock()
        
        result = await service.send_webhook(
            job_id=job_id,
            webhook_url="https://example.com/webhook",
            payload={"status": "done"},
            secret="test_secret"
        )
    
    # Verify synchronous execution result
    assert result["success"] is True
    assert result["status_code"] == 200
