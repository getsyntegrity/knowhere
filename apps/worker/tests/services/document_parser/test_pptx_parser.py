"""Tests for parse_pptx — fallback behavior and iLoveAPI hardening."""
import pytest
import requests
from unittest.mock import patch, MagicMock

from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import UnavailableException
from app.services.document_parser.pptx_parser import parse_pptx


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
