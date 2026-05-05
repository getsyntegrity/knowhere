from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from shared.core.exceptions.domain_exceptions import ValidationException
from shared.utils import pinned_outbound_http


class _RedirectResponse:
    status = 302

    def stream(self, chunk_size: int) -> list[bytes]:
        return []

    def release_conn(self) -> None:
        return None

    def close(self) -> None:
        return None


class _RedirectConnectionPool:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs

    def urlopen(self, *args: object, **kwargs: object) -> _RedirectResponse:
        assert kwargs["redirect"] is False
        return _RedirectResponse()


class _SuccessResponse:
    status = 200

    def __init__(self) -> None:
        self.is_released = False
        self.is_closed = False

    def stream(self, chunk_size: int) -> list[bytes]:
        return [b"pdf", b""]

    def release_conn(self) -> None:
        self.is_released = True

    def close(self) -> None:
        self.is_closed = True


class _SuccessConnectionPool:
    calls: list[dict[str, Any]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs

    def urlopen(self, *args: object, **kwargs: object) -> _SuccessResponse:
        self.calls.append(
            {
                "init_args": self.args,
                "init_kwargs": self.kwargs,
                "urlopen_args": args,
                "urlopen_kwargs": kwargs,
            }
        )
        return _SuccessResponse()


def test_should_block_redirect_responses_and_remove_partial_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        pinned_outbound_http,
        "PinnedHTTPConnectionPool",
        _RedirectConnectionPool,
    )

    with pytest.raises(ValidationException):
        pinned_outbound_http.download_pinned_outbound_file(
            url="http://example.test/file.pdf",
            pinned_ip="93.184.216.34",
            timeout_seconds=300,
            user_agent="Knowhere-FileDownloader/1.0",
            temp_dir=str(tmp_path),
        )

    assert list(tmp_path.iterdir()) == []


def test_should_request_public_url_through_the_pinned_http_pool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _SuccessConnectionPool.calls = []
    monkeypatch.setattr(
        pinned_outbound_http,
        "PinnedHTTPConnectionPool",
        _SuccessConnectionPool,
    )

    result = pinned_outbound_http.download_pinned_outbound_file(
        url="http://example.test:8080/files/source.pdf?download=1",
        pinned_ip="93.184.216.34",
        timeout_seconds=300,
        user_agent="Knowhere-FileDownloader/1.0",
        temp_dir=str(tmp_path),
    )

    assert Path(result.temp_file_path).read_bytes() == b"pdf"

    call = _SuccessConnectionPool.calls[0]
    init_kwargs = call["init_kwargs"]
    urlopen_kwargs = call["urlopen_kwargs"]
    retry_config = init_kwargs["retries"]
    timeout = urlopen_kwargs["timeout"]

    assert call["init_args"] == ("example.test", 8080)
    assert init_kwargs["pinned_ip"] == "93.184.216.34"
    assert retry_config.total == 0
    assert retry_config.redirect == 0
    assert call["urlopen_args"] == ("GET", "/files/source.pdf?download=1")
    assert timeout.connect_timeout == 300
    assert timeout.read_timeout == 300
    assert urlopen_kwargs["preload_content"] is False
    assert urlopen_kwargs["redirect"] is False
    assert urlopen_kwargs["headers"] == {
        "User-Agent": "Knowhere-FileDownloader/1.0",
        "Host": "example.test:8080",
    }
