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
from shared.tests.fakes import FakeAsyncSession, FakeScalarResult
from shared.services.webhook.dispatcher import WebhookDispatcher, MAX_ATTEMPTS

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
    
    # Mock DB execute with smart side effect
    async def db_execute_side_effect(statement, *args, **kwargs):
        # Check if querying Job table (by checking table name in statement)
        try:
            # Naive check for table name in compiled statement or object structure
            # Since mocking is hard, we'll assume if it's NOT checking for ID of the event, it's the job query
            # But safer: check if table name "jobs" is involved
            if hasattr(statement, 'get_final_froms'):
                froms = statement.get_final_froms()
                if froms and froms[0].name == 'jobs':
                    return MagicMock(scalar_one_or_none=MagicMock(return_value="user_123"))
        except:
            pass
        
        # Fallback to standard fake behavior (returning storage items)
        return MagicMock(scalars=lambda: FakeScalarResult(fake_db.storage), scalar_one_or_none=lambda: fake_db.storage[0] if fake_db.storage else None)

    fake_db.execute = AsyncMock(side_effect=db_execute_side_effect)

    with patch("shared.services.webhook.dispatcher.get_db_context", 
               return_value=MagicMock(__aenter__=AsyncMock(return_value=fake_db), __aexit__=AsyncMock(return_value=None))), \
         patch("aiohttp.ClientSession.post", return_value=mock_response), \
         patch.object(dispatcher, "_resolve_secret", new_callable=AsyncMock) as mock_resolve:
        
        mock_resolve.return_value = "test_secret"
        
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
    
    # Mock DB execute with smart side effect
    async def db_execute_side_effect(statement, *args, **kwargs):
        try:
            if hasattr(statement, 'get_final_froms'):
                froms = statement.get_final_froms()
                if froms and froms[0].name == 'jobs':
                    return MagicMock(scalar_one_or_none=MagicMock(return_value="user_123"))
        except:
            pass
        return MagicMock(scalars=lambda: FakeScalarResult(fake_db.storage), scalar_one_or_none=lambda: fake_db.storage[0] if fake_db.storage else None)

    fake_db.execute = AsyncMock(side_effect=db_execute_side_effect)

    with patch("shared.services.webhook.dispatcher.get_db_context", 
               return_value=MagicMock(__aenter__=AsyncMock(return_value=fake_db), __aexit__=AsyncMock(return_value=None))), \
         patch("aiohttp.ClientSession.post", return_value=mock_response), \
         patch.object(dispatcher, "_resolve_secret", new_callable=AsyncMock) as mock_resolve:
        
        mock_resolve.return_value = "test_secret"
        
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
    
    # Mock DB execute with smart side effect
    async def db_execute_side_effect(statement, *args, **kwargs):
        try:
            if hasattr(statement, 'get_final_froms'):
                froms = statement.get_final_froms()
                if froms and froms[0].name == 'jobs':
                    return MagicMock(scalar_one_or_none=MagicMock(return_value="user_123"))
        except:
            pass
        return MagicMock(scalars=lambda: FakeScalarResult(fake_db.storage), scalar_one_or_none=lambda: fake_db.storage[0] if fake_db.storage else None)

    fake_db.execute = AsyncMock(side_effect=db_execute_side_effect)

    with patch("shared.services.webhook.dispatcher.get_db_context", 
               return_value=MagicMock(__aenter__=AsyncMock(return_value=fake_db), __aexit__=AsyncMock(return_value=None))), \
         patch("aiohttp.ClientSession.post", return_value=mock_response), \
         patch.object(dispatcher, "_resolve_secret", new_callable=AsyncMock) as mock_resolve:
        
        mock_resolve.return_value = "test_secret"
        
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
        payload={"status": "done"},
        status=WebhookEventStatus.DELIVERED,  # Already terminal
        attempts=1
    )
    fake_db.storage.append(event)
    
    with patch("shared.services.webhook.dispatcher.get_db_context", 
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
    FR-06: Signature is timestamped HMAC-SHA256 with format t=<timestamp>,v1=<hex>.
    Verify: Generated signature contains timestamp and valid HMAC.
    """
    payload = {"job_id": "123", "status": "done"}
    secret = "my_secret"
    
    signature = dispatcher._sign_payload(payload, secret)
    
    # New format: t=<timestamp>,v1=<signature>
    assert signature.startswith("t="), f"Signature should start with 't=', got: {signature}"
    assert ",v1=" in signature, f"Signature should contain ',v1=', got: {signature}"
    
    # Parse and verify
    parts = signature.split(",")
    timestamp_part = parts[0]  # t=<timestamp>
    sig_part = parts[1]        # v1=<signature>
    
    timestamp_str = timestamp_part.split("=")[1]
    sig_hex = sig_part.split("=")[1]
    
    # Verify timestamp is a valid int
    timestamp = int(timestamp_str)
    assert timestamp > 0, "Timestamp should be positive"
    
    # Verify signature is valid hex (64 chars for SHA256)
    assert len(sig_hex) == 64, f"Signature should be 64 hex chars, got {len(sig_hex)}"
    
    # Verify manual calculation matches
    payload_str = json.dumps(payload, separators=(',', ':'))
    signed_content = f"{timestamp_str}.{payload_str}"
    expected_sig = hmac.new(
        secret.encode(), signed_content.encode(), hashlib.sha256
    ).hexdigest()
    
    assert sig_hex == expected_sig, "Signature mismatch"
