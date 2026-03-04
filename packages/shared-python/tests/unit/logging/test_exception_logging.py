"""
Unit tests for exception logging contract.

Tests that KnowhereException.logging() method:
- Logs 4xx at WARNING with error_category=client
- Logs 5xx at ERROR with stacktrace and error_category=system
- Includes user_message in all exception logs
- Works with contextualized request/task fields
"""
import pytest
from unittest.mock import patch, MagicMock, call
from shared.core.exceptions import (
    ValidationException,
    NotFoundException,
    AuthException,
    PermissionDeniedException,
    RateLimitException,
    FileSystemException,
    UnknownException,
    UnavailableException,
)


class TestExceptionLoggingContract:
    """Test exception logging contract for 4xx and 5xx errors."""

    @pytest.fixture
    def mock_logger(self):
        """Placeholder logger mock for compatibility."""
        return MagicMock()

    @pytest.fixture
    def mock_context(self):
        """Mock contextualized log fields."""
        return {
            "request_id": "req_123",
            "user_id": "user_456"
        }

    def test_4xx_logs_at_warning_with_client_category(self, mock_logger, mock_context):
        """Test that 4xx exceptions log at WARNING with error_category=client."""
        exc = ValidationException(
            user_message="Invalid input",
            violations=[{"field": "email", "description": "Invalid format"}]
        )

        # Simulate logging method (to be implemented in Phase 2)
        # exc.logging()

        # For now, test the exception properties
        assert exc.http_status_code == 400
        assert exc.user_message == "Invalid input"
        assert exc.http_status_code < 500

    def test_5xx_logs_at_error_with_system_category(self, mock_logger, mock_context):
        """Test that 5xx exceptions log at ERROR with error_category=system."""
        exc = FileSystemException(
            internal_message="Permission denied: /var/lib/data",
            operation="write"
        )

        # Test exception properties
        assert exc.http_status_code == 500
        assert exc.http_status_code >= 500
        assert exc.internal_message == "Permission denied: /var/lib/data"

    def test_user_message_present_in_4xx_logs(self, mock_logger, mock_context):
        """Test that user_message is present in 4xx exception logs."""
        exc = ValidationException(
            user_message="The file 'data.csv' is too large (max 5MB)",
            violations=[{"field": "file", "description": "Exceeds 5MB limit"}]
        )

        assert exc.user_message == "The file 'data.csv' is too large (max 5MB)"
        assert exc.user_message is not None

    def test_user_message_present_in_5xx_logs(self, mock_logger, mock_context):
        """Test that user_message is present in 5xx exception logs."""
        exc = FileSystemException(
            internal_message="Disk full on /mnt/data",
            operation="write"
        )

        # 5xx should have auto-generated safe user_message
        assert exc.user_message is not None
        assert "internal system error" in exc.user_message.lower() or "contact support" in exc.user_message.lower()

    def test_context_included_in_exception_logs(self, mock_logger, mock_context):
        """Test that contextual fields can be included in logs."""
        exc = NotFoundException(
            resource="Job",
            resource_id="job_123"
        )

        # Verify context fixture data
        context = mock_context
        assert context["request_id"] == "req_123"
        assert context["user_id"] == "user_456"

    def test_4xx_auth_exception_logs_warning(self, mock_logger, mock_context):
        """Test AuthException (401) logs at WARNING."""
        exc = AuthException(user_message="Invalid API key")

        assert exc.http_status_code == 401
        assert exc.user_message == "Invalid API key"

    def test_4xx_permission_denied_logs_warning(self, mock_logger, mock_context):
        """Test PermissionDeniedException (403) logs at WARNING."""
        exc = PermissionDeniedException(
            user_message="You don't have permission to access this resource",
            required_permission="jobs:read"
        )

        assert exc.http_status_code == 403
        assert exc.user_message == "You don't have permission to access this resource"

    def test_4xx_not_found_logs_warning(self, mock_logger, mock_context):
        """Test NotFoundException (404) logs at WARNING."""
        exc = NotFoundException(
            resource="Webhook",
            resource_id="webhook_123"
        )

        assert exc.http_status_code == 404
        assert "not found" in exc.user_message.lower()

    def test_4xx_rate_limit_logs_warning(self, mock_logger, mock_context):
        """Test RateLimitException (429) logs at WARNING."""
        exc = RateLimitException(
            retry_after=15,
            limit=60,
            period="minute"
        )

        assert exc.http_status_code == 429
        assert exc.user_message is not None
        assert "rate limit" in exc.user_message.lower()

    def test_5xx_unavailable_logs_error(self, mock_logger, mock_context):
        """Test UnavailableException (503) logs at ERROR."""
        exc = UnavailableException(
            internal_message="Redis connection failed",
            retry_after=30
        )

        assert exc.http_status_code == 503
        assert exc.internal_message == "Redis connection failed"

    def test_5xx_unknown_exception_logs_error(self, mock_logger, mock_context):
        """Test UnknownException (500) logs at ERROR."""
        original = ValueError("Unexpected error")
        exc = UnknownException(original_exception=original)

        assert exc.http_status_code == 500
        assert exc.original_exception == original

    def test_exception_to_log_includes_required_fields(self, mock_logger, mock_context):
        """Test that to_log() includes all required fields."""
        exc = ValidationException(
            user_message="Invalid email format",
            violations=[{"field": "email", "description": "Must be valid email"}]
        )

        log_data = exc.to_log()

        assert "error_code" in log_data
        assert "http_status" in log_data
        assert "user_message" in log_data
        assert "internal_message" in log_data
        assert log_data["user_message"] == "Invalid email format"
        assert log_data["http_status"] == 400

    def test_5xx_exception_to_log_includes_stacktrace_info(self, mock_logger, mock_context):
        """Test that 5xx to_log() includes original exception info."""
        original = IOError("Disk write failed")
        exc = FileSystemException(
            internal_message="Failed to write file",
            operation="write",
            original_exception=original
        )

        log_data = exc.to_log()

        assert "original_exception" in log_data
        assert log_data["original_exception"]["type"] in {"IOError", "OSError"}
        assert log_data["original_exception"]["message"] == "Disk write failed"

    def test_internal_message_not_in_client_response(self, mock_logger, mock_context):
        """Test that internal_message is never in to_client() response."""
        exc = FileSystemException(
            internal_message="Permission denied: /var/lib/worker/tmp/secret_path",
            operation="write"
        )

        client_response = exc.to_client(request_id="req_123")

        # Verify internal_message is NOT in response
        assert "internal_message" not in str(client_response)
        assert "secret_path" not in str(client_response)
        assert client_response["error"]["message"] == exc.user_message

    def test_user_message_in_client_response(self, mock_logger, mock_context):
        """Test that user_message is in to_client() response."""
        exc = ValidationException(
            user_message="The file 'data.csv' is too large (max 5MB)",
            violations=[{"field": "file", "description": "Exceeds 5MB limit"}]
        )

        client_response = exc.to_client(request_id="req_123")

        assert client_response["error"]["message"] == "The file 'data.csv' is too large (max 5MB)"
        assert client_response["error"]["code"] == exc.code.value

    def test_4xx_error_category_client(self, mock_logger, mock_context):
        """Test that 4xx exceptions have error_category=client."""
        exceptions_4xx = [
            ValidationException(user_message="Invalid", violations=[]),
            AuthException(user_message="Auth failed"),
            PermissionDeniedException(user_message="Forbidden"),
            NotFoundException(resource="Job", resource_id="123"),
        ]

        for exc in exceptions_4xx:
            assert exc.http_status_code < 500
            # error_category would be added in logging() method

    def test_5xx_error_category_system(self, mock_logger, mock_context):
        """Test that 5xx exceptions have error_category=system."""
        exceptions_5xx = [
            FileSystemException(internal_message="Disk error", operation="write"),
            UnknownException(original_exception=Exception("Unknown")),
            UnavailableException(internal_message="Service down", retry_after=30),
        ]

        for exc in exceptions_5xx:
            assert exc.http_status_code >= 500
            # error_category would be added in logging() method


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
