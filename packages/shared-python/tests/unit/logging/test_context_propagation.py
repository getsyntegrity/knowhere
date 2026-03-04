"""
Unit tests for context propagation using contextvars.

Tests that log context is properly set, retrieved, and isolated across execution contexts.
"""
import pytest
from contextvars import ContextVar
from unittest.mock import patch, MagicMock


# Mock context propagation utilities (to be implemented in Phase 1)
_log_context: ContextVar[dict] = ContextVar("log_context", default={})


def get_log_context() -> dict:
    """Get current log context."""
    return _log_context.get().copy()


def set_log_context(**kwargs):
    """Set log context fields."""
    current = _log_context.get().copy()
    current.update(kwargs)
    return _log_context.set(current)


def reset_log_context(token):
    """Reset log context to previous state."""
    _log_context.reset(token)


class TestContextPropagation:
    """Test context propagation utilities."""

    def test_get_empty_context(self):
        """Test getting context when none is set."""
        _log_context.set({})
        context = get_log_context()
        assert context == {}

    def test_set_and_get_context(self):
        """Test setting and retrieving context."""
        token = set_log_context(request_id="req_123", user_id="user_456")
        context = get_log_context()

        assert context["request_id"] == "req_123"
        assert context["user_id"] == "user_456"

        reset_log_context(token)

    def test_context_update_preserves_existing(self):
        """Test that updating context preserves existing fields."""
        token1 = set_log_context(request_id="req_123")
        token2 = set_log_context(job_id="job_789")

        context = get_log_context()
        assert context["request_id"] == "req_123"
        assert context["job_id"] == "job_789"

        reset_log_context(token2)
        reset_log_context(token1)

    def test_context_isolation_between_resets(self):
        """Test that context is properly isolated with reset."""
        token1 = set_log_context(request_id="req_123")
        context1 = get_log_context()

        token2 = set_log_context(request_id="req_456")
        context2 = get_log_context()

        assert context2["request_id"] == "req_456"

        reset_log_context(token2)
        context3 = get_log_context()
        assert context3["request_id"] == "req_123"

        reset_log_context(token1)

    def test_context_copy_independence(self):
        """Test that get_log_context returns a copy, not reference."""
        token = set_log_context(request_id="req_123")
        context1 = get_log_context()
        context1["modified"] = "value"

        context2 = get_log_context()
        assert "modified" not in context2

        reset_log_context(token)

    def test_nested_context_updates(self):
        """Test nested context updates and resets."""
        token1 = set_log_context(request_id="req_123", level=1)

        token2 = set_log_context(job_id="job_456", level=2)
        context2 = get_log_context()
        assert context2["request_id"] == "req_123"
        assert context2["job_id"] == "job_456"
        assert context2["level"] == 2

        token3 = set_log_context(task_id="task_789", level=3)
        context3 = get_log_context()
        assert context3["request_id"] == "req_123"
        assert context3["job_id"] == "job_456"
        assert context3["task_id"] == "task_789"
        assert context3["level"] == 3

        reset_log_context(token3)
        context_after_3 = get_log_context()
        assert "task_id" not in context_after_3
        assert context_after_3["level"] == 2

        reset_log_context(token2)
        context_after_2 = get_log_context()
        assert "job_id" not in context_after_2
        assert context_after_2["level"] == 1

        reset_log_context(token1)

    def test_context_with_none_values(self):
        """Test that None values are stored in context."""
        token = set_log_context(request_id=None, user_id="user_123")
        context = get_log_context()

        assert "request_id" in context
        assert context["request_id"] is None
        assert context["user_id"] == "user_123"

        reset_log_context(token)

    def test_context_overwrite_existing_key(self):
        """Test that setting same key overwrites previous value."""
        token1 = set_log_context(request_id="req_123")
        token2 = set_log_context(request_id="req_456")

        context = get_log_context()
        assert context["request_id"] == "req_456"

        reset_log_context(token2)
        reset_log_context(token1)

    def test_multiple_fields_in_single_call(self):
        """Test setting multiple fields in a single call."""
        token = set_log_context(
            request_id="req_123",
            user_id="user_456",
            job_id="job_789",
            task_id="task_abc"
        )

        context = get_log_context()
        assert context["request_id"] == "req_123"
        assert context["user_id"] == "user_456"
        assert context["job_id"] == "job_789"
        assert context["task_id"] == "task_abc"

        reset_log_context(token)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
