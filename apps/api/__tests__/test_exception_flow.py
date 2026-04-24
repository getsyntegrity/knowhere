"""
API Exception Flow Tests

Tests to verify the KnowhereException handling works correctly across all endpoints.
Each test verifies:
1. Correct HTTP status code
2. Response follows standard format: {success: false, error: {...}}
3. Error code matches expected ErrorCode enum value
4. Details contain expected fields

Test Categories:
- Validation exceptions (400 INVALID_ARGUMENT)
- Rate limit exceptions (429 RESOURCE_EXHAUSTED)
- Authentication exceptions (401 UNAUTHENTICATED)
- Not found exceptions (404 NOT_FOUND)
- Permission denied exceptions (403 PERMISSION_DENIED)
"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


# =============================================================================
# Helper Functions
# =============================================================================


def assert_error_response(response_json: dict, expected_code: str):
    """Assert the response follows the standard error format."""
    assert response_json.get("success") is False, "Expected success=false"

    error = response_json.get("error")
    assert error is not None, "Expected error object in response"
    assert error.get("code") == expected_code, (
        f"Expected code={expected_code}, got {error.get('code')}"
    )
    assert "message" in error, "Expected message in error"
    assert "request_id" in error, "Expected request_id in error"


# =============================================================================
# Validation Exception Tests (400 INVALID_ARGUMENT)
# =============================================================================


class TestValidationExceptions:
    """Tests for validation-related exceptions."""

    @pytest.mark.asyncio
    async def test_create_job_missing_file_name(
        self, authenticated_client: AsyncClient
    ):
        """
        Test: Create job with source_type=file but no file_name
        Expected: 400 INVALID_ARGUMENT
        """
        response = await authenticated_client.post(
            "/api/v1/jobs",
            json={
                "source_type": "file",
                # file_name is missing
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert_error_response(data, "INVALID_ARGUMENT")

        # Check violations in details
        details = data["error"].get("details", {})
        violations = details.get("violations", [])
        assert len(violations) > 0, "Expected violations in details"

    @pytest.mark.asyncio
    async def test_create_job_missing_source_url(
        self, authenticated_client: AsyncClient
    ):
        """
        Test: Create job with source_type=url but no source_url
        Expected: 400 INVALID_ARGUMENT
        """
        response = await authenticated_client.post(
            "/api/v1/jobs",
            json={
                "source_type": "url",
                # source_url is missing
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert_error_response(data, "INVALID_ARGUMENT")

    @pytest.mark.asyncio
    async def test_create_job_unsupported_file_type(
        self, authenticated_client: AsyncClient
    ):
        """
        Test: Create job with unsupported file type
        Expected: 400 INVALID_ARGUMENT
        """
        response = await authenticated_client.post(
            "/api/v1/jobs",
            json={
                "source_type": "file",
                "file_name": "document.xyz",  # Unsupported extension
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert_error_response(data, "INVALID_ARGUMENT")

    @pytest.mark.asyncio
    async def test_pydantic_validation_error(self, authenticated_client: AsyncClient):
        """
        Test: Send invalid JSON that fails Pydantic validation
        Expected: 400 or 422 INVALID_ARGUMENT (via RequestValidationError handler)
        """
        response = await authenticated_client.post(
            "/api/v1/jobs",
            json={
                # source_type is required but missing
            },
        )

        # Should be 400 or 422 (Pydantic validation)
        assert response.status_code in [400, 422]
        data = response.json()

        # Check standard error format
        assert data.get("success") is False


# =============================================================================
# Authentication Exception Tests (401 UNAUTHENTICATED)
# =============================================================================


class TestAuthenticationExceptions:
    """Tests for authentication-related exceptions."""

    @pytest.mark.asyncio
    async def test_missing_auth_header(self, client: AsyncClient):
        """
        Test: Request without Authorization header
        Expected: 401 UNAUTHENTICATED
        """
        response = await client.get("/api/v1/jobs/page")

        assert response.status_code == 401
        data = response.json()
        assert_error_response(data, "UNAUTHENTICATED")

    @pytest.mark.asyncio
    async def test_invalid_bearer_token(self, client: AsyncClient):
        """
        Test: Request with invalid Bearer token
        Expected: 401 UNAUTHENTICATED
        """
        response = await client.get(
            "/api/v1/jobs/page", headers={"Authorization": "Bearer invalid_token_12345"}
        )

        assert response.status_code == 401
        data = response.json()
        assert_error_response(data, "UNAUTHENTICATED")

    @pytest.mark.asyncio
    async def test_malformed_auth_header(self, client: AsyncClient):
        """
        Test: Request with malformed Authorization header
        Expected: 401 UNAUTHENTICATED
        """
        response = await client.get(
            "/api/v1/jobs/page", headers={"Authorization": "NotBearer token"}
        )

        assert response.status_code == 401
        data = response.json()
        assert_error_response(data, "UNAUTHENTICATED")


# =============================================================================
# Not Found Exception Tests (404 NOT_FOUND)
# =============================================================================


class TestNotFoundExceptions:
    """Tests for not-found-related exceptions."""

    @pytest.mark.asyncio
    async def test_nonexistent_job(self, authenticated_client: AsyncClient):
        """
        Test: Get a job that doesn't exist
        Expected: 404 NOT_FOUND
        """
        # Mock the job repository to return None
        with patch("app.api.v1.routes.jobs.JobRepository") as MockJobRepo:
            mock_repo = MockJobRepo.return_value
            mock_repo.get_job_by_id = AsyncMock(return_value=None)

            response = await authenticated_client.get("/api/v1/jobs/job_nonexistent123")

        assert response.status_code == 404
        data = response.json()
        assert_error_response(data, "NOT_FOUND")

        # Check resource info in details
        details = data["error"].get("details", {})
        assert details.get("resource") == "Job"

    @pytest.mark.asyncio
    async def test_nonexistent_route(self, client: AsyncClient):
        """
        Test: Request a route that doesn't exist
        Expected: 404 NOT_FOUND
        """
        response = await client.get("/api/v1/nonexistent_endpoint")

        assert response.status_code == 404
        data = response.json()
        assert_error_response(data, "NOT_FOUND")


# =============================================================================
# Rate Limit Exception Tests (429 RESOURCE_EXHAUSTED)
# =============================================================================


class TestRateLimitExceptions:
    """Tests for rate limit exceptions."""

    @pytest.mark.asyncio
    async def test_rate_limit_response_format_documentation(self):
        """
        Test: Document and verify expected rate limit error response format

        When rate limited, the API should return:
        {
            "success": false,
            "error": {
                "code": "RESOURCE_EXHAUSTED",
                "message": "Rate limit exceeded. Please retry after 15 seconds.",
                "request_id": "...",
                "details": {
                    "reason": "RATE_LIMIT_EXCEEDED",
                    "retry_after": 15,
                    "limit": 60,
                    "period": "minute"
                }
            }
        }

        Response headers should include:
            Retry-After: 15
        """
        # Document the expected format for rate limit responses
        # This test verifies the RateLimitException class produces correct output
        from shared.core.exceptions.domain_exceptions import RateLimitException

        exc = RateLimitException(retry_after=15, limit=60, period="minute")

        # Verify exception properties
        assert exc.retry_after == 15
        assert exc.limit == 60
        assert exc.period == "minute"
        assert exc.http_status_code == 429

        # Verify to_client() output format
        result = exc.to_client("test_request_id")
        assert result["success"] is False
        assert result["error"]["code"] == "RESOURCE_EXHAUSTED"
        assert "retry_after" in result["error"]["details"]
        assert result["error"]["details"]["retry_after"] == 15
        assert result["error"]["details"]["limit"] == 60
        assert result["error"]["details"]["period"] == "minute"


# =============================================================================
# Error Response Format Tests
# =============================================================================


class TestErrorResponseFormat:
    """Tests to verify consistent error response format across all handlers."""

    @pytest.mark.asyncio
    async def test_root_endpoint_accessible(self, client: AsyncClient):
        """
        Test: Root endpoint should be accessible without auth
        Expected: 200 OK
        """
        response = await client.get("/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_error_contains_request_id(self, client: AsyncClient):
        """
        Test: All error responses should contain a request_id
        """
        response = await client.get("/api/v1/jobs/page")  # No auth header

        assert response.status_code == 401
        data = response.json()

        error = data.get("error", {})
        assert "request_id" in error, "Error response must contain request_id"
        assert error["request_id"] is not None

    @pytest.mark.asyncio
    async def test_error_never_contains_internal_details(self, client: AsyncClient):
        """
        Test: Error responses should never leak internal details
        """
        response = await client.get("/api/v1/jobs/page")  # No auth header

        assert response.status_code == 401
        data = response.json()

        error = data.get("error", {})
        # Should not contain internal_message, stack traces, or sensitive info
        assert "internal_message" not in error
        assert "traceback" not in error
        assert "stack_trace" not in error


# =============================================================================
# Integration smoke test
# =============================================================================


class TestSmokeTest:
    """Quick smoke tests to verify API is running."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test the root endpoint returns successfully."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["ok", "healthy", None] or "message" in data


class TestFileLimitations:
    """Tests for file type limitations."""

    @pytest.mark.asyncio
    async def test_unsupported_file_type(self, authenticated_client: AsyncClient):
        """
        Test: .exe file
        Expected: 400 INVALID_ARGUMENT
        """
        response = await authenticated_client.post(
            "/api/v1/jobs",
            json={"source_type": "file", "file_name": "malware.exe", "file_size": 1024},
        )

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported file type" in data["error"]["message"]
