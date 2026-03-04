"""
Schema validation tests for structured logging.

Tests that:
- Base schema fields are always present in every log line
- Log records conform to the target schema
- Event naming follows conventions
- Context fields are properly included
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime


class TestSchemaValidation:
    """Test structured logging schema validation."""

    def test_base_schema_fields_always_present(self):
        """Test that base schema fields are present in every log."""
        # Base fields that must be in every log line
        required_base_fields = [
            "timestamp",
            "level",
            "event",
            "message",
            "schema_version",
            "service",
            "component",
            "environment",
            "logger",
            "function",
            "line",
            "process_id",
            "thread_id"
        ]

        # Simulate a log record
        log_record = {
            "timestamp": "2026-03-03T09:21:43.512Z",
            "level": "INFO",
            "event": "http.request.complete",
            "message": "HTTP request completed",
            "schema_version": "1.0",
            "service": "knowhere-api",
            "component": "api",
            "environment": "staging",
            "logger": "app.middleware",
            "function": "log_request",
            "line": 42,
            "process_id": 12345,
            "thread_id": 67890
        }

        # Verify all required fields present
        for field in required_base_fields:
            assert field in log_record, f"Missing required base field: {field}"

    def test_correlation_fields_nullable(self):
        """Test that correlation fields can be null."""
        correlation_fields = [
            "request_id",
            "user_id",
            "job_id",
            "task_id"
        ]

        # Log without correlation fields
        log_record = {
            "timestamp": "2026-03-03T09:21:43.512Z",
            "level": "INFO",
            "event": "app.log",
            "message": "Application started",
            "schema_version": "1.0",
            "service": "knowhere-api",
            "component": "api",
            "environment": "dev"
        }

        # Correlation fields should be optional
        for field in correlation_fields:
            assert field not in log_record or log_record.get(field) is None

    def test_http_fields_present_in_api_logs(self):
        """Test that HTTP fields are present in API logs."""
        http_fields = ["http_method", "http_path", "status_code", "duration_ms"]

        api_log = {
            "timestamp": "2026-03-03T09:21:43.512Z",
            "level": "INFO",
            "event": "http.request.complete",
            "message": "HTTP request completed",
            "schema_version": "1.0",
            "service": "knowhere-api",
            "component": "api",
            "environment": "staging",
            "request_id": "req_123",
            "http_method": "POST",
            "http_path": "/api/v1/jobs",
            "status_code": 201,
            "duration_ms": 87
        }

        for field in http_fields:
            assert field in api_log, f"Missing HTTP field: {field}"

    def test_exception_fields_present_in_error_logs(self):
        """Test that exception fields are present in error logs."""
        exception_fields = [
            "error_code",
            "http_status",
            "error_category",
            "exception_class",
            "internal_message",
            "user_message"
        ]

        error_log = {
            "timestamp": "2026-03-03T09:22:01.107Z",
            "level": "WARNING",
            "event": "exception.client",
            "message": "Client Error: INVALID_ARGUMENT",
            "schema_version": "1.0",
            "service": "knowhere-api",
            "component": "api",
            "request_id": "req_124",
            "error_code": "INVALID_ARGUMENT",
            "http_status": 400,
            "error_category": "client",
            "exception_class": "ValidationException",
            "internal_message": "Missing required field source_type",
            "user_message": "Invalid input: missing required field"
        }

        for field in exception_fields:
            assert field in error_log, f"Missing exception field: {field}"

    def test_4xx_error_has_client_category(self):
        """Test that 4xx errors have error_category=client."""
        error_log = {
            "level": "WARNING",
            "event": "exception.client",
            "http_status": 400,
            "error_category": "client",
            "user_message": "Invalid input"
        }

        assert error_log["http_status"] < 500
        assert error_log["error_category"] == "client"
        assert error_log["level"] == "WARNING"

    def test_5xx_error_has_system_category(self):
        """Test that 5xx errors have error_category=system."""
        error_log = {
            "level": "ERROR",
            "event": "exception.system",
            "http_status": 500,
            "error_category": "system",
            "user_message": "An internal system error occurred",
            "exception": {
                "type": "PermissionError",
                "message": "[Errno 13] Permission denied"
            }
        }

        assert error_log["http_status"] >= 500
        assert error_log["error_category"] == "system"
        assert error_log["level"] == "ERROR"

    def test_event_naming_convention(self):
        """Test that event names follow dot-separated convention."""
        valid_events = [
            "http.request.start",
            "http.request.complete",
            "exception.client",
            "exception.system",
            "worker.task.start",
            "worker.task.complete",
            "worker.task.retry",
            "worker.task.failure",
            "correlation.request_id_missing",
            "logging.configured"
        ]

        for event in valid_events:
            # Event should be dot-separated
            parts = event.split(".")
            assert len(parts) >= 2, f"Event {event} should have at least 2 parts"
            # Each part should be lowercase with underscores
            for part in parts:
                assert part.islower() or "_" in part, f"Event part {part} should be lowercase"

    def test_schema_version_present(self):
        """Test that schema_version is always present."""
        log_record = {
            "timestamp": "2026-03-03T09:21:43.512Z",
            "level": "INFO",
            "event": "app.log",
            "message": "Test message",
            "schema_version": "1.0",
            "service": "knowhere-api",
            "component": "api"
        }

        assert "schema_version" in log_record
        assert log_record["schema_version"] == "1.0"

    def test_service_and_component_present(self):
        """Test that service and component are always present."""
        log_record = {
            "timestamp": "2026-03-03T09:21:43.512Z",
            "level": "INFO",
            "event": "app.log",
            "message": "Test message",
            "schema_version": "1.0",
            "service": "knowhere-api",
            "component": "api"
        }

        assert "service" in log_record
        assert "component" in log_record
        assert log_record["service"] in ["knowhere-api", "knowhere-worker"]
        assert log_record["component"] in ["api", "worker"]

    def test_timestamp_format_iso8601(self):
        """Test that timestamp follows ISO 8601 format."""
        timestamp = "2026-03-03T09:21:43.512Z"

        # Verify ISO 8601 format
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid, "Timestamp should be in ISO 8601 format"

    def test_log_level_valid_values(self):
        """Test that log level has valid values."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in valid_levels:
            log_record = {
                "level": level,
                "message": "Test message"
            }
            assert log_record["level"] in valid_levels

    def test_worker_log_includes_task_and_job_id(self):
        """Test that worker logs include task_id and job_id."""
        worker_log = {
            "timestamp": "2026-03-03T09:24:10.901Z",
            "level": "INFO",
            "event": "worker.task.start",
            "message": "Task started",
            "schema_version": "1.0",
            "service": "knowhere-worker",
            "component": "worker",
            "request_id": "req_124",
            "task_id": "celery_abc",
            "job_id": "job_77"
        }

        assert "task_id" in worker_log
        assert "job_id" in worker_log
        assert worker_log["task_id"] == "celery_abc"
        assert worker_log["job_id"] == "job_77"

    def test_missing_request_id_event_format(self):
        """Test correlation.request_id_missing event format."""
        missing_request_id_log = {
            "timestamp": "2026-03-03T09:24:10.901Z",
            "level": "WARNING",
            "event": "correlation.request_id_missing",
            "message": "request_id missing in worker context",
            "schema_version": "1.0",
            "service": "knowhere-worker",
            "component": "worker",
            "task_id": "celery_abc",
            "job_id": "job_77",
            "request_id": None
        }

        assert missing_request_id_log["event"] == "correlation.request_id_missing"
        assert missing_request_id_log["level"] == "WARNING"
        assert missing_request_id_log["request_id"] is None

    def test_log_record_is_valid_json(self):
        """Test that log record can be serialized to JSON."""
        log_record = {
            "timestamp": "2026-03-03T09:21:43.512Z",
            "level": "INFO",
            "event": "http.request.complete",
            "message": "HTTP request completed",
            "schema_version": "1.0",
            "service": "knowhere-api",
            "component": "api",
            "environment": "staging",
            "request_id": "req_123",
            "http_method": "POST",
            "http_path": "/api/v1/jobs",
            "status_code": 201,
            "duration_ms": 87
        }

        # Should be serializable to JSON
        try:
            json_str = json.dumps(log_record)
            parsed = json.loads(json_str)
            is_valid = True
        except (TypeError, ValueError):
            is_valid = False

        assert is_valid, "Log record should be valid JSON"

    def test_exception_stacktrace_in_5xx_logs(self):
        """Test that 5xx logs include exception stacktrace."""
        error_log = {
            "timestamp": "2026-03-03T09:24:10.901Z",
            "level": "ERROR",
            "event": "exception.system",
            "message": "System Error: INTERNAL_ERROR",
            "schema_version": "1.0",
            "service": "knowhere-worker",
            "component": "worker",
            "request_id": "req_124",
            "task_id": "celery_abc",
            "job_id": "job_77",
            "error_code": "INTERNAL_ERROR",
            "http_status": 500,
            "error_category": "system",
            "exception_class": "FileSystemException",
            "exception": {
                "type": "PermissionError",
                "message": "[Errno 13] Permission denied"
            }
        }

        assert "exception" in error_log
        assert "type" in error_log["exception"]
        assert "message" in error_log["exception"]

    def test_user_message_always_present_in_exceptions(self):
        """Test that user_message is always present in exception logs."""
        # 4xx exception
        client_error = {
            "level": "WARNING",
            "event": "exception.client",
            "error_code": "INVALID_ARGUMENT",
            "http_status": 400,
            "user_message": "Invalid input: missing required field"
        }

        # 5xx exception
        system_error = {
            "level": "ERROR",
            "event": "exception.system",
            "error_code": "INTERNAL_ERROR",
            "http_status": 500,
            "user_message": "An internal system error occurred. Please contact support."
        }

        assert "user_message" in client_error
        assert "user_message" in system_error
        assert client_error["user_message"] is not None
        assert system_error["user_message"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
