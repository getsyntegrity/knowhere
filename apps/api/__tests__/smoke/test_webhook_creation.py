"""
API Smoke Tests - Organized by Requirement
Tests verify side effects (DB persistence, MQ publish) without importing Worker code.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4

from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
from shared.tests.fakes import FakeAsyncSession, FakeCeleryApp
from app.services.webhook_service import WebhookService
from shared.services.webhook.dispatcher import WebhookDispatcher

# --- Fixtures ---
@pytest.fixture
def fake_db():
    return FakeAsyncSession()

@pytest.fixture
def fake_celery():
    return FakeCeleryApp()

@pytest.fixture
def webhook_service():
    return WebhookService()

# =============================================================================
# FR-01: Event Trigger
# =============================================================================
@pytest.mark.asyncio
async def test_fr01_event_trigger_creates_pending_event(fake_db, webhook_service):
    """
    FR-01: When a job completes, a WebhookEvent is created with PENDING status.
    Verify: Event persisted in DB with correct fields.
    """
    job_id = str(uuid4())
    
    event = await webhook_service.create_job_completion_event(
        db=fake_db,
        job_id=job_id,
        webhook_url="https://example.com/webhook",
        webhook_secret="test_secret"
    )
    
    
    # Verify DB Side Effect
    # create_job_completion_event calls flush(), so it's in fake_db.new, not storage
    assert event in fake_db.new
    assert event.status == WebhookEventStatus.PENDING
    assert event.job_id == job_id
    assert event.attempts == 0

@pytest.mark.asyncio
async def test_fr01_event_trigger_sends_celery_task(fake_db, fake_celery, webhook_service):
    """
    FR-01: After event creation, a Celery task is dispatched.
    Verify: Task sent to broker with correct event_id.
    """
    job_id = str(uuid4())
    event_id = str(uuid4())
    
    with patch("shared.core.celery_app.get_celery_app", return_value=fake_celery):
        success = await webhook_service.publish_to_queue(event_id=event_id)
    
    # Verify MQ Side Effect
    assert success is True
    assert len(fake_celery.tasks) == 1
    task = fake_celery.tasks[0]
    assert task["name"] == "app.core.tasks.webhook_tasks.dispatch_webhook_task"
    assert task["args"][0] == event_id


# =============================================================================
# FR-02: Dynamic Configuration
# =============================================================================
@pytest.mark.asyncio
async def test_fr02_rejects_invalid_url_scheme(fake_db, webhook_service):
    """
    FR-02: Webhook URL must be http or https.
    Verify: ftp:// URL is rejected.
    """
    from shared.core.exceptions.webhook_exceptions import WebhookConfigException
    
    with pytest.raises(WebhookConfigException) as exc:
        await webhook_service.create_job_completion_event(
            db=fake_db,
            job_id=str(uuid4()),
            webhook_url="ftp://invalid.com/webhook",
            webhook_secret="secret"
        )
    assert "http://" in exc.value.user_message or "https://" in exc.value.user_message

@pytest.mark.asyncio
async def test_fr02_rejects_empty_secret(fake_db, webhook_service):
    """
    FR-02: Webhook secret is required.
    Verify: Empty secret is rejected.
    """
    from shared.core.exceptions.webhook_exceptions import WebhookConfigException
    
    # Mock _get_webhook_secret to return None so we can test validation failure
    with patch.object(webhook_service, '_get_webhook_secret', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        
        with pytest.raises(WebhookConfigException) as exc:
            await webhook_service.create_job_completion_event(
                db=fake_db,
                job_id=str(uuid4()),
                webhook_url="https://example.com/webhook",
                webhook_secret=""
            )
        assert "secret" in exc.value.user_message.lower()


# =============================================================================
# FR-09: Manual Trigger
# =============================================================================
@pytest.mark.asyncio
async def test_fr09_manual_trigger_dispatcher(fake_db):
    """
    FR-09: Manual trigger uses WebhookDispatcher directly.
    Verify: _send_webhook returns success and injects manually mark.
    """
    dispatcher = WebhookDispatcher()
    job_id = str(uuid4())
    
    event = WebhookEvent(
        job_id=job_id,
        target_url="https://example.com/webhook",
        secret="test_secret",
        payload={"status": "manual_test"},
        attempts=0  # Explicitly init attempts
    )
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value="OK")
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None
    
    with patch("aiohttp.ClientSession.post", return_value=mock_response):
        success, status_code, duration_ms, error = await dispatcher._send_webhook(
            db=fake_db,
            event=event,
            is_manual=True
        )
    
    # Verify result
    assert success is True
    assert status_code == 200
    
    # Verify Log persistence 
    # _send_webhook calls commit(), so log should be in storage
    logs = [obj for obj in fake_db.storage if str(type(obj)).find('WebhookLog') != -1]
    
    # If storage is empty, check .new just in case commit() was mocked differently
    if not logs:
         logs = [obj for obj in fake_db.new if str(type(obj)).find('WebhookLog') != -1]

    assert len(logs) == 1, f"Expected 1 log, found {len(logs)}. Storage: {len(fake_db.storage)}, New: {len(fake_db.new)}"
    log = logs[0]
    
    # Check that manually mark was injected
    assert log.event_id is None
    assert log.request_payload['payload']['trigger'] == 'manual'
