from types import SimpleNamespace

from app.api.v1.routes.jobs import _build_error_response


def test_build_error_response_parses_stringified_error_details():
    job = SimpleNamespace(
        error_message="Failed to parse the PDF file",
        error_code="INVALID_ARGUMENT",
        job_id="job_123",
    )

    error = _build_error_response(
        job,
        {
            "error_details": '{"file_type": "pdf", "reason": "PARSING_FAILED"}',
        },
    )

    assert error is not None
    assert error.details == {
        "file_type": "pdf",
        "reason": "PARSING_FAILED",
    }
