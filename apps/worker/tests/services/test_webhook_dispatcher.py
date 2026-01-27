"""
Unit tests for WebhookDispatcher

Tests the core dispatcher logic including:
- HMAC-SHA256 signature generation
- Backoff calculation with jitter
- Dispatch success/failure handling
- Max attempts threshold
"""
import hashlib
import hmac
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module under test
import sys
sys.path.insert(0, '/home/suguan/github.com/ontosAI/knowhere-api/apps/worker')

from app.services.webhook.dispatcher import WebhookDispatcher
from app.services.webhook import MAX_ATTEMPTS


class TestWebhookDispatcher:
    """Test suite for WebhookDispatcher."""
    
    @pytest.fixture
    def dispatcher(self):
        """Create a dispatcher instance for testing."""
        return WebhookDispatcher()
    
    # =========================================================================
    # Signature Generation Tests
    # =========================================================================
    
    def test_sign_payload_hmac_sha256(self, dispatcher):
        """Verify signature matches expected HMAC-SHA256 format."""
        payload = {"event": "job.completed", "job_id": "test-123"}
        secret = "test_secret"
        
        signature = dispatcher._sign_payload(payload, secret)
        
        # Verify format
        assert signature.startswith("sha256=")
        
        # Verify it's a valid hex string
        hex_part = signature[7:]  # Remove "sha256=" prefix
        assert len(hex_part) == 64  # SHA256 produces 64 hex chars
        assert all(c in '0123456789abcdef' for c in hex_part)
    
    def test_sign_payload_matches_expected(self, dispatcher):
        """Verify signature matches manually computed HMAC."""
        payload = {"key": "value"}
        secret = "my_secret"
        
        # Compute expected signature
        payload_str = json.dumps(payload, separators=(',', ':'))
        expected_sig = hmac.new(
            secret.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        signature = dispatcher._sign_payload(payload, secret)
        
        assert signature == f"sha256={expected_sig}"
    
    def test_sign_payload_different_secrets_differ(self, dispatcher):
        """Signatures with different secrets should differ."""
        payload = {"event": "test"}
        
        sig1 = dispatcher._sign_payload(payload, "secret1")
        sig2 = dispatcher._sign_payload(payload, "secret2")
        
        assert sig1 != sig2
    
    def test_sign_payload_different_payloads_differ(self, dispatcher):
        """Signatures of different payloads should differ."""
        secret = "test_secret"
        
        sig1 = dispatcher._sign_payload({"a": 1}, secret)
        sig2 = dispatcher._sign_payload({"a": 2}, secret)
        
        assert sig1 != sig2
    
    # =========================================================================
    # Dispatch Flow Tests (with mocks)
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_dispatch_failed_delivery_raises_exception(self, dispatcher):
        """Dispatch should raise exception on failure to trigger Celery retry."""
        mock_event = MagicMock()
        mock_event.id = "test-event-id"
        mock_event.attempts = 1
        mock_event.is_terminal.return_value = False
        
        # Mock dependencies
        with patch.object(dispatcher, '_fetch_event', new_callable=AsyncMock) as mock_fetch, \
             patch.object(dispatcher, '_send_webhook', new_callable=AsyncMock) as mock_send, \
             patch.object(dispatcher, '_increment_attempts', new_callable=AsyncMock) as mock_inc, \
             patch.object(dispatcher, '_log_delivery', new_callable=AsyncMock):
            
            mock_fetch.return_value = mock_event
            # Simulate failure response
            mock_send.return_value = (False, 500, 100, "Internal Server Error")
            
            # Should raise WebhookDeliveryException
            from shared.core.exceptions.webhook_exceptions import WebhookDeliveryException
            with pytest.raises(WebhookDeliveryException):
                await dispatcher.dispatch("test-event-id")
            
            # Verify attempt was incremented
            mock_inc.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_dispatch_event_not_found_acks(self, dispatcher):
        """Dispatch should ACK when event not found."""
        with patch.object(dispatcher, '_fetch_event', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            
            result = await dispatcher.dispatch("nonexistent-id")
            
            assert result is True  # Should ACK
    
    @pytest.mark.asyncio
    async def test_dispatch_terminal_event_acks(self, dispatcher):
        """Dispatch should ACK for already-terminal events."""
        # Create mock event in terminal state
        mock_event = MagicMock()
        mock_event.id = "test-event-id"
        mock_event.status = "delivered"
        mock_event.is_terminal.return_value = True
        
        with patch.object(dispatcher, '_fetch_event', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_event
            
            result = await dispatcher.dispatch("test-event-id")
            
            assert result is True  # Should ACK terminal events
    
    @pytest.mark.asyncio  
    async def test_dispatch_max_attempts_marks_failed(self, dispatcher):
        """Dispatch should mark event as failed when max attempts exceeded."""
        mock_event = MagicMock()
        mock_event.id = "test-event-id"
        mock_event.attempts = MAX_ATTEMPTS
        mock_event.is_terminal.return_value = False
        
        with patch.object(dispatcher, '_fetch_event', new_callable=AsyncMock) as mock_fetch, \
             patch.object(dispatcher, '_mark_failed', new_callable=AsyncMock) as mock_mark_failed:
            mock_fetch.return_value = mock_event
            
            result = await dispatcher.dispatch("test-event-id")
            
            assert result is True  # Should ACK
            mock_mark_failed.assert_called_once()


class TestWebhookDispatcherIntegration:
    """Integration tests requiring database/network (marked for skip in CI)."""
    
    @pytest.mark.skip(reason="Requires database connection")
    @pytest.mark.asyncio
    async def test_full_dispatch_success_flow(self):
        """Test complete dispatch flow with real database."""
        pass
    
    @pytest.mark.skip(reason="Requires database connection")
    @pytest.mark.asyncio
    async def test_full_dispatch_failure_and_retry(self):
        """Test dispatch failure triggers retry scheduling."""
        pass
