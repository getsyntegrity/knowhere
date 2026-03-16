"""Tests for MinerU S3 URL-based ingestion mode."""
from typing import cast

import pytest

from app.services.document_parser import mineru_pdf_service, pdf_parser
from app.services.document_parser.mineru_quota_manager import (
    MinerUQuotaManager,
    MinerUTokenConfig,
)
from shared.core.exceptions.domain_exceptions import (
    MinerUServiceException,
    UnavailableException,
)
from shared.services.redis.redis_sync_service import SyncRedisService

fakeredis = pytest.importorskip("fakeredis")


class FakeSyncRedisService:
    def __init__(self, client):
        self.client = client

    def get(self, key, default=None):
        value = self.client.get(key)
        return default if value is None else value

    def set(self, key, value, ttl=None, ex=None):
        expire = ex or ttl
        return bool(self.client.set(key, value, ex=expire))

    def eval(self, script, keys, args=None):
        return self.client.eval(
            script, len(keys), *(list(keys) + list(args or []))
        )


class FakeResponse:
    def __init__(self, status_code, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json_data


def _build_manager(fake_server=None):
    redis_client = fakeredis.FakeRedis(
        server=fake_server, decode_responses=True
    )
    manager = MinerUQuotaManager(
        cast(SyncRedisService, FakeSyncRedisService(redis_client)),
        [
            MinerUTokenConfig("primary", "sk-1", rpm_limit=300, daily_limit=10000),
        ],
    )
    return manager, redis_client


def test_submit_url_task_success(monkeypatch):
    """_submit_url_task posts presigned URL and returns batch_id + token_id."""
    manager, _ = _build_manager()
    monkeypatch.setattr(
        mineru_pdf_service, "get_mineru_quota_manager", lambda: manager
    )

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        captured["auth"] = headers.get("Authorization")
        return FakeResponse(200, {
            "code": 0,
            "data": {"batch_id": "batch-url-1"},
        })

    fake_session = type(
        "S", (), {"post": staticmethod(fake_post)}
    )()
    monkeypatch.setattr(
        mineru_pdf_service, "get_mineru_session", lambda: fake_session
    )

    batch_id, token_id = mineru_pdf_service._submit_url_task(
        "https://s3.example.com/presigned?token=abc", "report.pdf"
    )

    assert batch_id == "batch-url-1"
    assert token_id == "primary"
    assert captured["url"].endswith("/extract/task/batch")
    assert captured["payload"]["files"] == [
        {"url": "https://s3.example.com/presigned?token=abc"}
    ]
    assert captured["payload"]["is_ocr"] is True
    assert captured["payload"]["model_version"] == "vlm"


def test_submit_url_task_non_200_raises(monkeypatch):
    """_submit_url_task raises MinerUServiceException on non-200 response."""
    manager, _ = _build_manager()
    monkeypatch.setattr(
        mineru_pdf_service, "get_mineru_quota_manager", lambda: manager
    )

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(500, text="Internal Server Error")

    fake_session = type("S", (), {"post": staticmethod(fake_post)})()
    monkeypatch.setattr(
        mineru_pdf_service, "get_mineru_session", lambda: fake_session
    )

    with pytest.raises(MinerUServiceException) as exc_info:
        mineru_pdf_service._submit_url_task(
            "https://s3.example.com/presigned", "report.pdf"
        )
    assert "URL task submission failed" in exc_info.value.internal_message


def test_submit_url_task_rate_limit_raises(monkeypatch):
    """_submit_url_task raises UnavailableException on rate limit response."""
    manager, _ = _build_manager()
    monkeypatch.setattr(
        mineru_pdf_service, "get_mineru_quota_manager", lambda: manager
    )

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(200, {
            "code": -1,
            "msg": "Rate limit exceeded",
        })

    fake_session = type("S", (), {"post": staticmethod(fake_post)})()
    monkeypatch.setattr(
        mineru_pdf_service, "get_mineru_session", lambda: fake_session
    )

    with pytest.raises(UnavailableException) as exc_info:
        mineru_pdf_service._submit_url_task(
            "https://s3.example.com/presigned", "report.pdf"
        )
    assert exc_info.value.period == "minute"


def test_parse_via_full_uses_url_mode_in_staging(monkeypatch, tmp_path):
    """In non-development env with s3_key, uses URL mode (no upload)."""
    monkeypatch.setattr(
        "shared.core.config.settings.ENVIRONMENT", "staging"
    )
    manager, _ = _build_manager()
    monkeypatch.setattr(
        mineru_pdf_service, "get_mineru_quota_manager", lambda: manager
    )

    calls = []

    def fake_generate_download_url(s3_key, expires_in=3600):
        calls.append(("presign", s3_key, expires_in))
        return {"download_url": f"https://s3.example.com/{s3_key}?presigned=1"}

    monkeypatch.setattr(
        "app.services.storage.sync_storage_service.generate_download_url",
        fake_generate_download_url,
    )

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(("submit_url", url))
        return FakeResponse(200, {
            "code": 0,
            "data": {"batch_id": "batch-url-2"},
        })

    fake_session = type(
        "S", (), {"post": staticmethod(fake_post)}
    )()
    monkeypatch.setattr(
        mineru_pdf_service, "get_mineru_session", lambda: fake_session
    )

    def fake_poll(status_url, task_id, output_dir, get_status, preferred_token_id):
        calls.append(("poll", task_id, preferred_token_id))

    monkeypatch.setattr(
        mineru_pdf_service, "poll_mineru_task", fake_poll
    )

    output_dir = str(tmp_path / "output")
    mineru_pdf_service.parse_via_full(
        "/tmp/sample.pdf", "sample.pdf", output_dir,
        s3_key="uploads/sample.pdf",
    )

    assert calls[0][0] == "presign"
    assert calls[0][1] == "uploads/sample.pdf"
    assert calls[1][0] == "submit_url"
    assert "/extract/task/batch" in calls[1][1]
    assert calls[2] == ("poll", "batch-url-2", "primary")


def test_parse_via_full_uses_direct_upload_in_development(
    monkeypatch, tmp_path
):
    """In development env, falls back to direct upload even with s3_key."""
    monkeypatch.setattr(
        "shared.core.config.settings.ENVIRONMENT", "development"
    )
    manager, _ = _build_manager()
    monkeypatch.setattr(
        mineru_pdf_service, "get_mineru_quota_manager", lambda: manager
    )

    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(("post", url))
        return FakeResponse(200, {
            "code": 0,
            "data": {
                "batch_id": "batch-direct-1",
                "file_urls": ["https://oss.example/upload"],
            },
        })

    def fake_put(url, data=None, timeout=None):
        calls.append(("put", url))
        return FakeResponse(200)

    fake_session = type(
        "S", (),
        {"post": staticmethod(fake_post), "put": staticmethod(fake_put)},
    )()
    monkeypatch.setattr(
        mineru_pdf_service, "get_mineru_session", lambda: fake_session
    )

    def fake_poll(status_url, task_id, output_dir, get_status, preferred_token_id):
        calls.append(("poll", task_id))

    monkeypatch.setattr(
        mineru_pdf_service, "poll_mineru_task", fake_poll
    )

    local_pdf = tmp_path / "sample.pdf"
    local_pdf.write_bytes(b"%PDF-1.4\n")

    mineru_pdf_service.parse_via_full(
        str(local_pdf), "sample.pdf", str(tmp_path / "output"),
        s3_key="uploads/sample.pdf",
    )

    # Should use file-urls/batch (direct upload), not extract/task/batch
    assert any("/file-urls/batch" in c[1] for c in calls if c[0] == "post")
    assert any(c[0] == "put" for c in calls)
    assert calls[-1] == ("poll", "batch-direct-1")


def test_parse_pdfs_threads_s3_key_to_upload_and_parse(monkeypatch, tmp_path):
    """parse_pdfs passes s3_key through to upload_and_parse."""
    captured = {}

    def fake_upload_and_parse(pdf_url, filename, output_dir, s3_key=None):
        captured["s3_key"] = s3_key
        captured["filename"] = filename
        (tmp_path / "output" / "full.md").write_text("# parsed")

    def fake_parse_md(output_dir, source_type, file_path, base_llm_paras, relative_root=None):
        return {"ok": True}

    monkeypatch.setattr(pdf_parser, "upload_and_parse", fake_upload_and_parse)
    monkeypatch.setattr(pdf_parser, "parse_md", fake_parse_md)

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    pdf_parser.parse_pdfs(
        str(tmp_path / "sample.pdf"),
        filename="sample.pdf",
        output_dir=str(output_dir),
        base_llm_paras={"foo": "bar"},
        s3_key="uploads/sample.pdf",
    )

    assert captured["s3_key"] == "uploads/sample.pdf"
    assert captured["filename"] == "sample.pdf"


def test_parse_pdfs_s3_key_defaults_to_none(monkeypatch, tmp_path):
    """parse_pdfs passes None s3_key when not provided."""
    captured = {}

    def fake_upload_and_parse(pdf_url, filename, output_dir, s3_key=None):
        captured["s3_key"] = s3_key
        (tmp_path / "output" / "full.md").write_text("# parsed")

    def fake_parse_md(output_dir, source_type, file_path, base_llm_paras, relative_root=None):
        return {"ok": True}

    monkeypatch.setattr(pdf_parser, "upload_and_parse", fake_upload_and_parse)
    monkeypatch.setattr(pdf_parser, "parse_md", fake_parse_md)

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    pdf_parser.parse_pdfs(
        str(tmp_path / "sample.pdf"),
        filename="sample.pdf",
        output_dir=str(output_dir),
        base_llm_paras={},
    )

    assert captured["s3_key"] is None
