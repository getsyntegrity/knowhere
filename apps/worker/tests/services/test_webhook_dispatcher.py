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
from app.services.webhook import JITTER_FACTOR, MAX_ATTEMPTS, BASE_DELAY_SECONDS


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
    # Backoff Calculation Tests
    # =========================================================================
    
    def test_calculate_backoff_first_attempt(self, dispatcher):
        """First attempt should use base delay with jitter."""
        delay = dispatcher._calculate_backoff(1)
        
        # Delay should be within ±JITTER_FACTOR of BASE_DELAY_SECONDS
        min_delay = BASE_DELAY_SECONDS * (1 - JITTER_FACTOR)
        max_delay = BASE_DELAY_SECONDS * (1 + JITTER_FACTOR)
        
        assert min_delay <= delay <= max_delay
    
    def test_calculate_backoff_exponential_growth(self, dispatcher):
        """Backoff should grow exponentially with attempt number."""
        delays = [dispatcher._calculate_backoff(i) for i in range(1, 6)]
        
        # Each delay should be roughly double the previous (accounting for jitter)
        for i in range(1, len(delays)):
            # The ratio should be approximately 2 (with jitter tolerance)
            ratio = delays[i] / delays[i-1]
            # Allow for jitter variance (factor of ~1.5 to ~2.5)
            assert 1.4 < ratio < 2.8, f"Ratio at attempt {i+1}: {ratio}"
    
    def test_calculate_backoff_with_jitter_variation(self, dispatcher):
        """Multiple calls for same attempt should produce different values (jitter)."""
        attempt = 3
        delays = [dispatcher._calculate_backoff(attempt) for _ in range(10)]
        
        # With jitter, not all delays should be identical
        unique_delays = set(delays)
        assert len(unique_delays) > 1, "Jitter should produce variation"
    
    # =========================================================================
    # Retry Queue Selection Tests
    # =========================================================================
    
    def test_get_retry_queue_for_attempt_mapping(self, dispatcher):
        """Verify correct retry queue selection based on attempt."""
        assert dispatcher.get_retry_queue_for_attempt(1) == "wait.1m"
        assert dispatcher.get_retry_queue_for_attempt(2) == "wait.10m"
        assert dispatcher.get_retry_queue_for_attempt(3) == "wait.30m"
        assert dispatcher.get_retry_queue_for_attempt(4) == "wait.2h"
        assert dispatcher.get_retry_queue_for_attempt(5) == "wait.6h"
        # Beyond max attempts, still use longest delay
        assert dispatcher.get_retry_queue_for_attempt(6) == "wait.6h"
    
    # =========================================================================
    # Dispatch Flow Tests (with mocks)
    # =========================================================================
    
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
