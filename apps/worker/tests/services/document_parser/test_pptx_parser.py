"""Tests for parse_pptx — fallback behavior and iLoveAPI hardening."""
import os

import pytest
import requests
from subprocess import CompletedProcess
from unittest.mock import patch, MagicMock

from shared.core.logging import LogEvent
from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import (
    FileSystemException,
    LibreOfficeServiceException,
    UnavailableException,
)
from app.services.document_parser.pptx_parser import (
    _pptx_bytes_to_pdf_bytes,
    parse_pptx,
    pptx_to_pdf_libreoffice,
)


@pytest.fixture(autouse=True)
def mock_load_file_bytes(monkeypatch):
    monkeypatch.setattr("app.services.document_parser.pptx_parser.load_file_bytes", lambda p, file_url: b"fake_pptx_data")


@pytest.fixture(autouse=True)
def reset_quota_manager_singleton():
    """Reset the singleton before and after each test to prevent cross-test leakage."""
    import shared.utils.iloveapi_quota_manager as mod
    mod._iloveapi_quota_manager = None
    yield
    mod._iloveapi_quota_manager = None


# ------------------------------------------------------------------
# Fallback: missing keys → LibreOffice
# ------------------------------------------------------------------

def test_parse_pptx_iloveapi_missing_keys(monkeypatch):
    monkeypatch.setattr(settings, "ILOVEAPI_KEYS", "", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "", raising=False)

    with patch("app.services.document_parser.pptx_parser._parse_pptx_via_libreoffice") as mock_fallback:
        mock_fallback.return_value = "parsed_df"
        result = parse_pptx(
            pptx_path="test.pptx",
            filename="test.pptx",
            output_dir="/tmp",
            base_llm_paras={},
            strategy="to_pdf_api"
        )
        assert result == "parsed_df"
        mock_fallback.assert_called_once()


# ------------------------------------------------------------------
# Fallback: token pool exhausted → LibreOffice
# ------------------------------------------------------------------

def test_parse_pptx_iloveapi_exhausted(monkeypatch):
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "pub", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "sec", raising=False)

    def mock_acquire(*args, **kwargs):
        raise UnavailableException(internal_message="exhausted", limit=25, period="minute", retry_after=60, user_message="busy")

    with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.acquire_request", side_effect=mock_acquire):
        with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.acquire_inflight", return_value=True):
            with patch("app.services.document_parser.pptx_parser._parse_pptx_via_libreoffice") as mock_fallback:
                mock_fallback.return_value = "parsed_df"
                result = parse_pptx(
                    pptx_path="test.pptx",
                    filename="test.pptx",
                    output_dir="/tmp",
                    base_llm_paras={},
                    strategy="to_pdf_api"
                )
                assert result == "parsed_df"
                mock_fallback.assert_called_once()


# ------------------------------------------------------------------
# Fallback: iLoveAPI timeout → LibreOffice
# ------------------------------------------------------------------

def test_parse_pptx_iloveapi_timeout(monkeypatch):
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "pub", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "sec", raising=False)

    def mock_get(*args, **kwargs):
        raise requests.exceptions.Timeout("API timed out")

    with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.acquire_inflight", return_value=True):
        with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.release_inflight"):
            with patch("app.services.document_parser.pptx_parser.requests.get", side_effect=mock_get):
                with patch("app.services.document_parser.pptx_parser._parse_pptx_via_libreoffice") as mock_fallback:
                    mock_fallback.return_value = "parsed_df"
                    result = parse_pptx(
                        pptx_path="test.pptx",
                        filename="test.pptx",
                        output_dir="/tmp",
                        base_llm_paras={},
                        strategy="to_pdf_api"
                    )
                    assert result == "parsed_df"
                    mock_fallback.assert_called_once()


# ------------------------------------------------------------------
# Fallback: HTTP error (500) → LibreOffice
# ------------------------------------------------------------------

def test_parse_pptx_iloveapi_http_error_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "pub", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "sec", raising=False)

    def mock_get(*args, **kwargs):
        res = MagicMock()
        res.status_code = 500
        res.headers = {}
        res.raise_for_status.side_effect = requests.exceptions.HTTPError(response=res)
        return res

    with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.acquire_inflight", return_value=True):
        with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.release_inflight"):
            with patch("app.services.document_parser.pptx_parser.requests.get", side_effect=mock_get):
                with patch("app.services.document_parser.pptx_parser._parse_pptx_via_libreoffice") as mock_fallback:
                    mock_fallback.return_value = "parsed_df"
                    result = parse_pptx(
                        pptx_path="test.pptx",
                        filename="test.pptx",
                        output_dir="/tmp",
                        base_llm_paras={},
                        strategy="to_pdf_api"
                    )
                    assert result == "parsed_df"
                    mock_fallback.assert_called_once()


# ------------------------------------------------------------------
# Fallback: concurrency limit exceeded → LibreOffice
# ------------------------------------------------------------------

def test_parse_pptx_concurrency_exceeded_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "pub", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "sec", raising=False)

    with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.acquire_inflight", return_value=False):
        with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.get_inflight_count", return_value=5):
            with patch("app.services.document_parser.pptx_parser._parse_pptx_via_libreoffice") as mock_fallback:
                mock_fallback.return_value = "parsed_df"
                result = parse_pptx(
                    pptx_path="test.pptx",
                    filename="test.pptx",
                    output_dir="/tmp",
                    base_llm_paras={},
                    strategy="to_pdf_api"
                )
                assert result == "parsed_df"
                mock_fallback.assert_called_once()


# ------------------------------------------------------------------
# Fallback: 429 response → rate limit + LibreOffice
# ------------------------------------------------------------------

def test_parse_pptx_iloveapi_429_response_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "pub", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "sec", raising=False)

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "30"}
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)

    with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.acquire_inflight", return_value=True):
        with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.release_inflight"):
            with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.mark_rate_limited") as mock_mark:
                with patch("app.services.document_parser.pptx_parser.requests.get", return_value=mock_response):
                    with patch("app.services.document_parser.pptx_parser._parse_pptx_via_libreoffice") as mock_fallback:
                        mock_fallback.return_value = "parsed_df"
                        result = parse_pptx(
                            pptx_path="test.pptx",
                            filename="test.pptx",
                            output_dir="/tmp",
                            base_llm_paras={},
                            strategy="to_pdf_api"
                        )
                        assert result == "parsed_df"
                        mock_fallback.assert_called_once()
                        # Verify rate-limit was registered
                        mock_mark.assert_called()


# ------------------------------------------------------------------
# Direct strategy: to_pdf never touches iLoveAPI
# ------------------------------------------------------------------

def test_parse_pptx_to_pdf_strategy_skips_iloveapi(monkeypatch):
    with patch("app.services.document_parser.pptx_parser._parse_pptx_via_libreoffice") as mock_lo:
        with patch("app.services.document_parser.pptx_parser._pptx_bytes_to_pdf_bytes") as mock_api:
            mock_lo.return_value = "parsed_df"
            result = parse_pptx(
                pptx_path="test.pptx",
                filename="test.pptx",
                output_dir="/tmp",
                base_llm_paras={},
                strategy="to_pdf"
            )
            assert result == "parsed_df"
            mock_lo.assert_called_once()
            mock_api.assert_not_called()


def test_parse_pptx_to_pdf_api_uploads_rendered_pdf_for_mineru_url_mode(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser._pptx_bytes_to_pdf_bytes",
        lambda pptx_data, filename: b"pdf-bytes",
    )
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser._render_pdf_to_image_pdf",
        lambda pdf_bytes: b"image-pdf-bytes",
    )

    captured: dict[str, object] = {}

    def fake_parse_pdfs(
        pdf_path,
        filename,
        output_dir,
        base_llm_paras,
        profile=None,
        relative_root=None,
        s3_key=None,
    ):
        captured["pdf_path"] = pdf_path
        captured["filename"] = filename
        captured["output_dir"] = output_dir
        captured["relative_root"] = relative_root
        captured["s3_key"] = s3_key
        return "parsed_df"

    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser.parse_pdfs",
        fake_parse_pdfs,
    )
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser.get_existing_mineru_source_s3_key",
        lambda s3_key: None,
    )

    result = parse_pptx(
        pptx_path="test.pptx",
        filename="test.pptx",
        output_dir=str(tmp_path),
        base_llm_paras={},
        strategy="to_pdf_api",
        job_id="job_123",
        relative_root="Default_Root/test.pptx",
    )

    assert result == "parsed_df"
    assert captured["filename"] == "test.pptx"
    assert captured["output_dir"] == str(tmp_path)
    assert captured["relative_root"] == "Default_Root/test.pptx"
    assert captured["s3_key"] == "transform/job_123.rendered.pdf"


def test_parse_pptx_to_pdf_api_reuses_rendered_pdf_on_rerun(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
    captured: dict[str, object] = {}

    def fake_parse_pdfs(
        pdf_path,
        filename,
        output_dir,
        base_llm_paras,
        profile=None,
        relative_root=None,
        s3_key=None,
    ):
        assert os.path.exists(pdf_path)
        with open(pdf_path, "rb") as file_obj:
            assert file_obj.read() == b"%PDF-1.4 cached rerun\n"
        captured["pdf_path"] = pdf_path
        captured["s3_key"] = s3_key
        return "parsed_df"

    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser.parse_pdfs",
        fake_parse_pdfs,
    )
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser._pptx_bytes_to_pdf_bytes",
        lambda *args, **kwargs: pytest.fail("rerun should reuse cached rendered PDF"),
    )
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser._render_pdf_to_image_pdf",
        lambda *args, **kwargs: pytest.fail("rerun should skip rendered PDF regeneration"),
    )
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser.load_file_bytes",
        lambda *args, **kwargs: pytest.fail("rerun should reuse cached rendered PDF before loading the source deck"),
    )
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser.get_existing_mineru_source_s3_key",
        lambda s3_key: s3_key,
    )
    download_calls: list[tuple[str, str, str]] = []

    def fake_download_s3_object_to_temp(s3_key: str, suffix: str, temp_dir: str) -> str:
        download_calls.append((s3_key, suffix, temp_dir))
        local_path = tmp_path / "cached-rendered.pdf"
        local_path.write_bytes(b"%PDF-1.4 cached rerun\n")
        return str(local_path)

    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser.download_s3_object_to_temp",
        fake_download_s3_object_to_temp,
    )

    result = parse_pptx(
        pptx_path="test.pptx",
        filename="test.pptx",
        output_dir=str(tmp_path),
        base_llm_paras={},
        strategy="to_pdf_api",
        job_id="job_123",
        relative_root="Default_Root/test.pptx",
    )

    assert result == "parsed_df"
    assert captured["pdf_path"] == str(tmp_path / "cached-rendered.pdf")
    assert captured["s3_key"] == "transform/job_123.rendered.pdf"
    assert download_calls == [
        ("transform/job_123.rendered.pdf", ".pdf", str(tmp_path))
    ]
    assert not os.path.exists(str(tmp_path / "cached-rendered.pdf"))


def test_parse_pptx_to_pdf_api_keeps_direct_upload_in_development(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development", raising=False)
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser._pptx_bytes_to_pdf_bytes",
        lambda pptx_data, filename: b"pdf-bytes",
    )
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser._render_pdf_to_image_pdf",
        lambda pdf_bytes: b"image-pdf-bytes",
    )

    captured: dict[str, object] = {}

    def fake_parse_pdfs(
        pdf_path,
        filename,
        output_dir,
        base_llm_paras,
        profile=None,
        relative_root=None,
        s3_key=None,
    ):
        captured["s3_key"] = s3_key
        return "parsed_df"

    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser.parse_pdfs",
        fake_parse_pdfs,
    )
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser.get_existing_mineru_source_s3_key",
        lambda *args, **kwargs: pytest.fail("development mode should not check rendered PDF cache"),
    )

    result = parse_pptx(
        pptx_path="test.pptx",
        filename="test.pptx",
        output_dir=str(tmp_path),
        base_llm_paras={},
        strategy="to_pdf_api",
        job_id="job_123",
        relative_root="Default_Root/test.pptx",
    )

    assert result == "parsed_df"
    assert captured["s3_key"] is None


# ------------------------------------------------------------------
# Inflight release on error: verify cleanup
# ------------------------------------------------------------------

def test_parse_pptx_releases_inflight_on_error(monkeypatch):
    """Verify that the in-flight slot is released even when conversion fails."""
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "pub", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "sec", raising=False)

    with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.acquire_inflight", return_value=True):
        with patch("shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.release_inflight") as mock_release:
            with patch("app.services.document_parser.pptx_parser.requests.get", side_effect=requests.exceptions.ConnectionError("connection refused")):
                with patch("app.services.document_parser.pptx_parser._parse_pptx_via_libreoffice") as mock_fallback:
                    mock_fallback.return_value = "parsed_df"
                    result = parse_pptx(
                        pptx_path="test.pptx",
                        filename="test.pptx",
                        output_dir="/tmp",
                        base_llm_paras={},
                        strategy="to_pdf_api"
                    )
                    assert result == "parsed_df"
                    # Verify release was called (cleanup in finally block)
                    mock_release.assert_called_once()


def test_parse_pptx_fail_open_does_not_release_inflight(monkeypatch):
    """Fail-open requests must not decrement another request's in-flight slot."""
    monkeypatch.setattr(settings, "ILOVEAPI_PUBLIC_KEY", "pub", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_SECRET_KEY", "sec", raising=False)

    with patch(
        "shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.acquire_inflight",
        return_value=None,
    ):
        with patch(
            "shared.utils.iloveapi_quota_manager.ILoveApiQuotaManager.release_inflight"
        ) as mock_release:
            with patch(
                "app.services.document_parser.pptx_parser._get_iloveapi_token_lease",
                return_value=("token", MagicMock(token_id="iloveapi-1")),
            ):
                with patch(
                    "app.services.document_parser.pptx_parser.requests.get",
                    side_effect=requests.exceptions.ConnectionError("connection refused"),
                ):
                    with patch(
                        "app.services.document_parser.pptx_parser._parse_pptx_via_libreoffice"
                    ) as mock_fallback:
                        mock_fallback.return_value = "parsed_df"
                        result = parse_pptx(
                            pptx_path="test.pptx",
                            filename="test.pptx",
                            output_dir="/tmp",
                            base_llm_paras={},
                            strategy="to_pdf_api"
                        )
                        assert result == "parsed_df"
                        mock_release.assert_not_called()


def test_pptx_to_pdf_libreoffice_uses_impress_export_filter(monkeypatch, tmp_path):
    soffice_path = tmp_path / "libreoffice"
    soffice_path.write_text("", encoding="utf-8")
    pptx_path = tmp_path / "test.pptx"
    pptx_path.write_bytes(b"pptx")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    expected_pdf_path = output_dir / "test.pdf"
    expected_pdf_path.write_bytes(b"pdf")

    run_mock = MagicMock(
        return_value=CompletedProcess(
            args=[],
            returncode=0,
            stdout="converted",
            stderr="",
        )
    )

    monkeypatch.setattr(settings, "LIBER_OFFICE", str(soffice_path), raising=False)
    monkeypatch.setattr("app.services.document_parser.pptx_parser.subprocess.run", run_mock)

    pdf_path, pdf_name = pptx_to_pdf_libreoffice(str(pptx_path), str(output_dir))

    assert pdf_path == str(expected_pdf_path)
    assert pdf_name == "test.pdf"
    convert_arg = run_mock.call_args.args[0][3]
    assert convert_arg.startswith("pdf:impress_pdf_Export:")


def test_pptx_to_pdf_libreoffice_raises_libreoffice_service_exception_when_output_missing(
    monkeypatch, tmp_path
):
    soffice_path = tmp_path / "libreoffice"
    soffice_path.write_text("", encoding="utf-8")
    pptx_path = tmp_path / "test.pptx"
    pptx_path.write_bytes(b"pptx")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    monkeypatch.setattr(settings, "LIBER_OFFICE", str(soffice_path), raising=False)
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(
            args=[],
            returncode=0,
            stdout="conversion reported success",
            stderr="store failed",
        ),
    )

    with pytest.raises(LibreOfficeServiceException) as exc_info:
        pptx_to_pdf_libreoffice(str(pptx_path), str(output_dir))

    assert exc_info.value.details == {
        "service": "libreoffice",
        "operation": "emit_pdf_output",
    }
    assert "did not produce the expected PDF output" in exc_info.value.internal_message
    assert "store failed" in exc_info.value.internal_message


def test_pptx_bytes_to_pdf_bytes_logs_http_error_response_details(monkeypatch):
    fake_logger = MagicMock()
    fake_logger.bind.return_value = fake_logger
    monkeypatch.setattr("app.services.document_parser.pptx_parser.logger", fake_logger)

    quota_manager = MagicMock()
    quota_manager.acquire_inflight.return_value = True
    monkeypatch.setattr(
        "shared.utils.iloveapi_quota_manager.get_iloveapi_quota_manager",
        lambda: quota_manager,
    )
    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser._get_iloveapi_token_lease",
        lambda: ("token", MagicMock(token_id="iloveapi-1")),
    )
    monkeypatch.setattr(settings, "ILOVEAPI_BASE_URL", "https://api.ilovepdf.com/v1", raising=False)
    monkeypatch.setattr(settings, "ILOVEAPI_TIMEOUT", 120, raising=False)

    start_response = MagicMock()
    start_response.status_code = 200
    start_response.json.return_value = {
        "server": "api39w.ilovepdf.com",
        "task": "ilove-task-1",
    }
    start_response.raise_for_status.return_value = None

    upload_response = MagicMock()
    upload_response.status_code = 200
    upload_response.json.return_value = {"server_filename": "server-file-1.pptx"}
    upload_response.raise_for_status.return_value = None

    process_response = MagicMock()
    process_response.status_code = 400
    process_response.text = '{"error":"bad request"}'
    process_response.headers = {"Content-Type": "application/json"}
    process_response.url = "https://api39w.ilovepdf.com/v1/process"
    process_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=process_response
    )

    with patch("app.services.document_parser.pptx_parser.requests.get", return_value=start_response):
        with patch(
            "app.services.document_parser.pptx_parser.requests.post",
            side_effect=[upload_response, process_response],
        ):
            with pytest.raises(requests.exceptions.HTTPError):
                _pptx_bytes_to_pdf_bytes(b"fake_pptx_data", "test.pptx")

    failure_logs = [
        call.kwargs
        for call in fake_logger.bind.call_args_list
        if call.kwargs.get("event") == LogEvent.ILOVEAPI_REQUEST_FAIL.value
    ]

    assert len(failure_logs) == 1
    assert failure_logs[0]["step"] == "process"
    assert failure_logs[0]["upstream_server"] == "api39w.ilovepdf.com"
    assert failure_logs[0]["upstream_task_id"] == "ilove-task-1"
    assert failure_logs[0]["upstream_server_filename"] == "server-file-1.pptx"
    assert failure_logs[0]["response_content_type"] == "application/json"
    assert failure_logs[0]["response_body"] == '{"error":"bad request"}'
    quota_manager.release_inflight.assert_called_once()
