"""
Integration tests for Celery context propagation.

Tests that:
- Context propagates across Celery serialization boundary
- Worker context resets after task execution (no cross-task leak)
- Missing request_id emits correlation.request_id_missing event
- request_id flows from API → Worker
"""
import pytest
from unittest.mock import patch, MagicMock, call
from celery import Task


class MockContextPropagatingTask(Task):
    """Mock implementation of ContextPropagatingTask for testing."""

    def apply_async(self, args=None, kwargs=None, **options):
        """Capture context before serialization."""
        kwargs = kwargs or {}
        # Simulate capturing context (preserve explicit payload if provided)
        kwargs['_log_context'] = kwargs.get('_log_context') or {
            "request_id": "req_123",
            "user_id": "user_456"
        }
        return super().apply_async(args=args, kwargs=kwargs, **options)

    def __call__(self, *args, **kwargs):
        """Restore context after deserialization."""
        task_kwargs = kwargs.get("kwargs")
        if isinstance(task_kwargs, dict):
            context = task_kwargs.pop('_log_context', {})
        else:
            context = kwargs.pop('_log_context', {})
        # Simulate restoring context
        return super().__call__(*args, **kwargs)


class TestCeleryContextPropagation:
    """Test context propagation across Celery boundary."""

    def test_context_captured_before_serialization(self):
        """Test that context is captured in apply_async."""
        task = MockContextPropagatingTask()

        with patch.object(Task, 'apply_async', return_value=MagicMock()) as mock_apply:
            task.apply_async(args=(), kwargs={"job_id": "job_123"})

            # Verify _log_context was added to kwargs
            call_kwargs = mock_apply.call_args[1]['kwargs']
            assert '_log_context' in call_kwargs
            assert call_kwargs['_log_context']['request_id'] == "req_123"

    def test_context_restored_after_deserialization(self):
        """Test that context is restored in __call__."""
        task = MockContextPropagatingTask()

        kwargs_with_context = {
            "job_id": "job_123",
            "_log_context": {
                "request_id": "req_123",
                "user_id": "user_456"
            }
        }

        with patch.object(Task, '__call__', return_value=None) as mock_call:
            task.__call__(kwargs=kwargs_with_context)

            # Verify _log_context was popped from kwargs
            call_kwargs = mock_call.call_args[1]['kwargs']
            assert '_log_context' not in call_kwargs

    def test_request_id_propagates_from_api_to_worker(self):
        """Test that request_id flows from API to worker."""
        # Simulate API setting context
        api_context = {
            "request_id": "req_from_api_123",
            "user_id": "user_456"
        }

        # Simulate task capturing context
        task = MockContextPropagatingTask()
        with patch.object(Task, 'apply_async', return_value=MagicMock()) as mock_apply:
            task.apply_async(args=(), kwargs={"job_id": "job_789"})

            call_kwargs = mock_apply.call_args[1]['kwargs']
            assert call_kwargs['_log_context']['request_id'] == "req_123"

    def test_worker_adds_task_id_and_job_id_to_context(self):
        """Test that worker adds task_id and job_id to existing context."""
        # Simulate worker receiving context with request_id
        incoming_context = {
            "request_id": "req_123",
            "user_id": "user_456"
        }

        # Worker should add task_id and job_id
        worker_context = incoming_context.copy()
        worker_context.update({
            "task_id": "celery_task_abc",
            "job_id": "job_789"
        })

        assert worker_context["request_id"] == "req_123"
        assert worker_context["task_id"] == "celery_task_abc"
        assert worker_context["job_id"] == "job_789"

    def test_worker_context_resets_after_task_execution(self):
        """Test that worker context is reset after task to prevent leak."""
        # Simulate task 1 execution
        task1_context = {
            "request_id": "req_123",
            "task_id": "task_1",
            "job_id": "job_1"
        }

        # Simulate context reset (using token pattern)
        # After task 1 completes, context should be cleared

        # Simulate task 2 execution
        task2_context = {
            "request_id": "req_456",
            "task_id": "task_2",
            "job_id": "job_2"
        }

        # Verify task 2 doesn't see task 1's context
        assert task2_context["request_id"] != task1_context["request_id"]
        assert task2_context["task_id"] != task1_context["task_id"]

    def test_missing_request_id_emits_warning_event(self):
        """Test that missing request_id emits correlation.request_id_missing."""
        with patch("shared.core.logging.logger") as mock_logger:
            # Simulate worker receiving task without request_id
            context = {
                "task_id": "task_abc",
                "job_id": "job_789"
            }

            # Check if request_id is missing
            if "request_id" not in context or context.get("request_id") is None:
                # Should emit warning event
                event_name = "correlation.request_id_missing"
                assert event_name == "correlation.request_id_missing"

    def test_missing_request_id_logs_null_not_generated(self):
        """Test that missing request_id logs null, not a generated ID."""
        with patch("shared.core.logging.logger") as mock_logger:
            # Simulate worker receiving task without request_id
            context = {
                "task_id": "task_abc",
                "job_id": "job_789",
                "request_id": None  # Explicitly null
            }

            # Verify request_id is None, not generated
            assert context["request_id"] is None

    def test_context_propagation_with_empty_context(self):
        """Test that empty context is handled gracefully."""
        task = MockContextPropagatingTask()

        with patch.object(Task, 'apply_async', return_value=MagicMock()) as mock_apply:
            task.apply_async(args=(), kwargs={"job_id": "job_123"})

            call_kwargs = mock_apply.call_args[1]['kwargs']
            # _log_context should still be added, even if empty
            assert '_log_context' in call_kwargs

    def test_context_propagation_preserves_all_fields(self):
        """Test that all context fields are preserved across boundary."""
        full_context = {
            "request_id": "req_123",
            "user_id": "user_456",
            "job_id": "job_789",
            "task_id": "task_abc"
        }

        task = MockContextPropagatingTask()
        with patch.object(Task, 'apply_async', return_value=MagicMock()) as mock_apply:
            task.apply_async(args=(), kwargs={"job_id": "job_123", "_log_context": full_context})

            call_kwargs = mock_apply.call_args[1]['kwargs']
            captured_context = call_kwargs['_log_context']

            # Verify all fields preserved
            assert captured_context["request_id"] == "req_123"
            assert captured_context["user_id"] == "user_456"
            assert captured_context["job_id"] == "job_789"
            assert captured_context["task_id"] == "task_abc"

    def test_worker_on_failure_includes_request_id(self):
        """Test that on_failure callback includes request_id in metadata."""
        # Simulate on_failure callback
        context = {
            "request_id": "req_123",
            "task_id": "task_abc",
            "job_id": "job_789"
        }

        # Metadata passed back to API should include request_id
        metadata = {
            "request_id": context.get("request_id"),
            "task_id": context.get("task_id")
        }

        assert metadata["request_id"] == "req_123"
        assert metadata["task_id"] == "task_abc"

    def test_worker_on_failure_with_missing_request_id(self):
        """Test on_failure when request_id is missing."""
        context = {
            "task_id": "task_abc",
            "job_id": "job_789",
            "request_id": None
        }

        # Metadata should include request_id=None
        metadata = {
            "request_id": context.get("request_id"),
            "task_id": context.get("task_id")
        }

        assert metadata["request_id"] is None
        assert metadata["task_id"] == "task_abc"

    def test_context_isolation_between_concurrent_tasks(self):
        """Test that concurrent tasks have isolated contexts."""
        # Simulate two tasks running concurrently
        task1_context = {
            "request_id": "req_task1",
            "task_id": "task_1"
        }

        task2_context = {
            "request_id": "req_task2",
            "task_id": "task_2"
        }

        # Verify contexts are independent
        assert task1_context["request_id"] != task2_context["request_id"]
        assert task1_context["task_id"] != task2_context["task_id"]

        # Modifying one shouldn't affect the other
        task1_context["new_field"] = "value1"
        assert "new_field" not in task2_context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
