"""
Worker Smoke Tests - Organized by Requirement
Tests verify side effects (DB updates, HTTP requests) without importing API code.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4
import json
import hmac
import hashlib

from shared.models.database.webhook import WebhookEvent, WebhookEventStatus
from shared.tests.fakes import FakeAsyncSession
from app.services.webhook.dispatcher import WebhookDispatcher, MAX_ATTEMPTS

# --- Fixtures ---
@pytest.fixture
def fake_db():
    return FakeAsyncSession()

@pytest.fixture
def dispatcher():
    return WebhookDispatcher()

def create_pending_event(fake_db, event_id=None, attempts=0):
    """Helper to seed a pending event in fake DB."""
    event = WebhookEvent(
        id=event_id or str(uuid4()),
        job_id=str(uuid4()),
        target_url="https://example.com/webhook",
        secret="test_secret",
        payload={"status": "done"},
        status=WebhookEventStatus.PENDING,
        attempts=attempts
    )
    fake_db.storage.append(event)
    return event


# =============================================================================
# FR-03: Retry Logic with Exponential Backoff
# =============================================================================
@pytest.mark.asyncio
async def test_fr03_failure_increments_attempts(fake_db, dispatcher):
    """
    FR-03: On failed delivery, attempts counter is incremented.
    Verify: attempts goes from 0 to 1 on 500 response.
    """
    event = create_pending_event(fake_db, attempts=0)
    
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None
    
    with patch("app.services.webhook.dispatcher.get_db_context", 
               return_value=MagicMock(__aenter__=AsyncMock(return_value=fake_db), __aexit__=AsyncMock(return_value=None))), \
         patch("aiohttp.ClientSession.post", return_value=mock_response):
        
        from shared.core.exceptions.webhook_exceptions import WebhookDeliveryException
        with pytest.raises(WebhookDeliveryException):
            await dispatcher.dispatch(event.id)
    
    assert event.attempts == 1

@pytest.mark.asyncio
async def test_fr03_max_attempts_marks_failed(fake_db, dispatcher):
    """
    FR-03: After MAX_ATTEMPTS, event is marked FAILED and no exception raised.
    Verify: Status becomes FAILED, no retry exception.
    """
    event = create_pending_event(fake_db, attempts=MAX_ATTEMPTS - 1)
    
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None
    
    with patch("app.services.webhook.dispatcher.get_db_context", 
               return_value=MagicMock(__aenter__=AsyncMock(return_value=fake_db), __aexit__=AsyncMock(return_value=None))), \
         patch("aiohttp.ClientSession.post", return_value=mock_response):
        
        result = await dispatcher.dispatch(event.id)
    
    assert result is True  # ACK to queue
    assert event.status == WebhookEventStatus.FAILED
    assert event.attempts == MAX_ATTEMPTS


# =============================================================================
# FR-04: At-Least-Once Delivery Semantics
# =============================================================================
@pytest.mark.asyncio
async def test_fr04_successful_delivery_marks_delivered(fake_db, dispatcher):
    """
    FR-04: On 2xx response, event is marked DELIVERED.
    Verify: Status transitions to DELIVERED.
    """
    event = create_pending_event(fake_db)
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None
    
    with patch("app.services.webhook.dispatcher.get_db_context", 
               return_value=MagicMock(__aenter__=AsyncMock(return_value=fake_db), __aexit__=AsyncMock(return_value=None))), \
         patch("aiohttp.ClientSession.post", return_value=mock_response):
        
        result = await dispatcher.dispatch(event.id)
    
    assert result is True
    assert event.status == WebhookEventStatus.DELIVERED
    assert event.attempts == 1


# =============================================================================
# FR-05: Idempotency
# =============================================================================
@pytest.mark.asyncio
async def test_fr05_skips_already_delivered_event(fake_db, dispatcher):
    """
    FR-05: If event is already DELIVERED, skip without sending.
    Verify: No HTTP request made, returns True immediately.
    """
    event = WebhookEvent(
        id=str(uuid4()),
        job_id=str(uuid4()),
        target_url="https://example.com/webhook",
        secret="test_secret",
        payload={"status": "done"},
        status=WebhookEventStatus.DELIVERED,  # Already terminal
        attempts=1
    )
    fake_db.storage.append(event)
    
    with patch("app.services.webhook.dispatcher.get_db_context", 
               return_value=MagicMock(__aenter__=AsyncMock(return_value=fake_db), __aexit__=AsyncMock(return_value=None))), \
         patch("aiohttp.ClientSession.post") as mock_post:
        
        result = await dispatcher.dispatch(event.id)
    
    assert result is True
    mock_post.assert_not_called()  # No HTTP request


# =============================================================================
# FR-06: Security (HMAC Signature)
# =============================================================================
def test_fr06_signature_matches_expected_format(dispatcher):
    """
    FR-06: Signature is HMAC-SHA256 of payload with format sha256=<hex>.
    Verify: Generated signature matches manual calculation.
    """
    payload = {"job_id": "123", "status": "done"}
    secret = "my_secret"
    
    signature = dispatcher._sign_payload(payload, secret)
    
    # Manual calculation
    payload_str = json.dumps(payload, separators=(',', ':'))
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_str.encode(), hashlib.sha256
    ).hexdigest()
    
    assert signature == expected
