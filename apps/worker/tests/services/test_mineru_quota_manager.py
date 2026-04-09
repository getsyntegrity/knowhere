from typing import Any, Optional, cast

import pytest
from redis.crc import key_slot

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
import shared.utils.quota_manager as quota_manager_module

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
        return self.client.eval(script, len(keys), *(list(keys) + list(args or [])))


def build_manager(
    *,
    tokens=None,
    decode_responses=True,
    fake_server=None,
):
    redis_client = fakeredis.FakeRedis(
        server=fake_server,
        decode_responses=decode_responses,
    )
    manager = MinerUQuotaManager(
        cast(SyncRedisService, FakeSyncRedisService(redis_client)),
        tokens
        or [
            MinerUTokenConfig("primary", "sk-1", rpm_limit=300, daily_limit=10000),
            MinerUTokenConfig("backup", "sk-2", rpm_limit=300, daily_limit=10000),
        ],
    )
    return manager, redis_client


def test_parse_token_specs_supports_json_entries():
    specs = MinerUQuotaManager.parse_token_specs(
        '[{"id":"primary","key":"sk-1","rpm_limit":250},{"id":"backup","key":"sk-2","daily_limit":9000}]',
        default_rpm_limit=300,
        default_daily_limit=10000,
    )

    assert [spec.token_id for spec in specs] == ["primary", "backup"]
    assert specs[0].api_key == "sk-1"
    assert specs[0].rpm_limit == 250
    assert specs[0].daily_limit == 10000
    assert specs[1].rpm_limit == 300
    assert specs[1].daily_limit == 9000


def test_acquire_request_skips_exhausted_token(monkeypatch):
    fixed_now = 1_700_000_000
    monkeypatch.setattr(quota_manager_module.time, "time", lambda: fixed_now)
    manager, redis_client = build_manager()
    primary_minute_key = manager._minute_key("primary", fixed_now)
    redis_client.set(primary_minute_key, 300, ex=12)

    lease = manager.acquire_request(operation="upload_url")

    assert lease.token_id == "backup"
    assert lease.api_key == "sk-2"


def test_acquire_request_reports_shortest_retry_window(monkeypatch):
    fixed_now = 1_700_000_000
    monkeypatch.setattr(quota_manager_module.time, "time", lambda: fixed_now)
    manager, redis_client = build_manager()

    primary_day_key = manager._day_key("primary", fixed_now)
    backup_minute_key = manager._minute_key("backup", fixed_now)
    redis_client.set(primary_day_key, 10000, ex=1800)
    redis_client.set(backup_minute_key, 300, ex=45)

    try:
        manager.acquire_request(operation="poll_status")
        assert False, "Expected UnavailableException"
    except UnavailableException as exc:
        assert exc.retry_after == 45
        assert exc.period == "minute"
        assert exc.user_message == "Document processing is busy right now. Please retry shortly."


def test_lua_reservation_enforces_rpm_limit():
    redis_service = cast(
        SyncRedisService,
        FakeSyncRedisService(fakeredis.FakeRedis(decode_responses=True)),
    )
    manager = MinerUQuotaManager(
        redis_service,
        [
            MinerUTokenConfig(
                token_id="primary",
                api_key="sk-1",
                rpm_limit=2,
                daily_limit=100,
            )
        ],
    )

    first = manager.acquire_request(operation="upload_url")
    second = manager.acquire_request(operation="upload_url")

    assert first.token_id == "primary"
    assert second.token_id == "primary"

    with pytest.raises(UnavailableException) as exc_info:
        manager.acquire_request(operation="upload_url")

    assert exc_info.value.period == "minute"
    assert 1 <= exc_info.value.retry_after <= 60
    assert exc_info.value.user_message == "Document processing is busy right now. Please retry shortly."


def test_lua_reservation_respects_daily_limit(monkeypatch):
    fixed_now = 1_700_000_000
    monkeypatch.setattr(quota_manager_module.time, "time", lambda: fixed_now)

    redis_service = cast(
        SyncRedisService,
        FakeSyncRedisService(fakeredis.FakeRedis(decode_responses=True)),
    )
    manager = MinerUQuotaManager(
        redis_service,
        [
            MinerUTokenConfig(
                token_id="primary",
                api_key="sk-1",
                rpm_limit=10,
                daily_limit=1,
            )
        ],
    )

    manager.acquire_request(operation="poll_status")

    with pytest.raises(UnavailableException) as exc_info:
        manager.acquire_request(operation="poll_status")

    assert exc_info.value.period == "day"
    assert exc_info.value.retry_after > 0
    assert exc_info.value.user_message == "Document processing is busy right now. Please retry shortly."


def test_lua_round_robin_uses_backup_token_after_cooldown():
    fake_server = fakeredis.FakeServer()
    redis_service = cast(
        SyncRedisService,
        FakeSyncRedisService(
            fakeredis.FakeRedis(server=fake_server, decode_responses=True)
        ),
    )
    manager = MinerUQuotaManager(
        redis_service,
        [
            MinerUTokenConfig("primary", "sk-1", rpm_limit=10, daily_limit=100),
            MinerUTokenConfig("backup", "sk-2", rpm_limit=10, daily_limit=100),
        ],
    )

    manager.mark_rate_limited("primary", retry_after=30)

    lease = manager.acquire_request(operation="upload_url")

    assert lease.token_id == "backup"


def test_quota_keys_share_cluster_hash_slot():
    fixed_now = 1_700_000_000
    manager, _ = build_manager()
    minute_key = manager._minute_key("primary", fixed_now)
    day_key = manager._day_key("primary", fixed_now)
    cooldown_key = manager._cooldown_key("primary")

    assert "{primary}" in minute_key
    assert "{primary}" in day_key
    assert "{primary}" in cooldown_key
    assert key_slot(minute_key.encode()) == key_slot(day_key.encode())
    assert key_slot(minute_key.encode()) == key_slot(cooldown_key.encode())


def test_upload_and_parse_reuses_preferred_token_for_polling(monkeypatch, tmp_path):
    fixed_now = 1_700_000_000
    monkeypatch.setattr(quota_manager_module.time, "time", lambda: fixed_now)

    redis_client = fakeredis.FakeRedis(decode_responses=True)
    redis_service = cast(SyncRedisService, FakeSyncRedisService(redis_client))
    manager = MinerUQuotaManager(
        redis_service,
        [
            MinerUTokenConfig("primary", "sk-primary", rpm_limit=10, daily_limit=100),
            MinerUTokenConfig("backup", "sk-backup", rpm_limit=10, daily_limit=100),
        ],
    )
    monkeypatch.setattr(mineru_pdf_service, "get_mineru_quota_manager", lambda: manager)

    mineru_calls = []
    captured_payloads: dict[str, Any] = {}

    class Response:
        def __init__(
            self,
            status_code: int,
            json_data: Optional[dict[str, Any]] = None,
            text: str = "",
            headers: Optional[dict[str, str]] = None,
        ) -> None:
            self.status_code = status_code
            self._json_data = json_data or {}
            self.text = text
            self.headers = headers or {}

        def json(self) -> dict[str, Any]:
            return self._json_data

    def fake_post(
        url: str,
        headers: Optional[dict[str, str]] = None,
        json: Optional[dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> Response:
        assert headers is not None
        captured_payloads["upload_url_request"] = json
        mineru_calls.append(("post", headers["Authorization"], url))
        return Response(
            200,
            {
                "code": 0,
                "data": {
                    "batch_id": "batch-1",
                    "file_urls": ["https://mineru-upload.example/file"],
                },
            },
        )

    def fake_put(url: str, data: Any = None, timeout: Any = None) -> Response:
        mineru_calls.append(("put", url, timeout))
        return Response(200, {})

    def fake_get(
        url: str,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Response:
        assert headers is not None
        mineru_calls.append(("get", headers["Authorization"], url))
        return Response(
            200,
            {
                "code": 0,
                "data": {
                    "extract_result": {
                        "state": "done",
                        "full_zip_url": "https://mineru-results.example/full.zip",
                    }
                },
            },
        )

    extracted = {}

    def fake_extract(url, dest_dir, keep_exts=None, exclude_patterns=None):
        extracted["url"] = url
        extracted["dest_dir"] = dest_dir

    fake_session = type("FakeSession", (), {"post": staticmethod(fake_post), "put": staticmethod(fake_put), "get": staticmethod(fake_get)})()
    monkeypatch.setattr(mineru_pdf_service, "get_mineru_session", lambda: fake_session)
    monkeypatch.setattr(mineru_pdf_service, "s3_download_extract_zip", fake_extract)

    local_pdf_path = tmp_path / "sample.pdf"
    local_pdf_path.write_bytes(b"%PDF-1.4\n")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    pdf_parser.upload_and_parse(str(local_pdf_path), "sample.pdf", str(output_dir))

    assert mineru_calls[0] == (
        "post",
        "Bearer sk-primary",
        "https://mineru.net/api/v4/file-urls/batch",
    )
    assert mineru_calls[1] == (
        "put",
        "https://mineru-upload.example/file",
        mineru_pdf_service.MINERU_UPLOAD_TIMEOUT,
    )
    assert mineru_calls[2] == (
        "get",
        "Bearer sk-primary",
        "https://mineru.net/api/v4/extract-results/batch/batch-1",
    )
    assert extracted["url"] == "https://mineru-results.example/full.zip"
    assert extracted["dest_dir"] == str(output_dir)
    assert captured_payloads["upload_url_request"] == {
        "files": [{"name": "sample.pdf", "is_ocr": True}],
        "enable_formula": True,
        "enable_table": True,
        "language": "auto",
        "model_version": "vlm",
    }

    minute_key = manager._minute_key("primary", fixed_now)
    day_key = manager._day_key("primary", fixed_now)
    assert int(redis_client.get(minute_key)) == 2
    assert int(redis_client.get(day_key)) == 2


def test_parse_pdfs_standard_route_uses_extracted_mineru_workflow(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    def fake_upload_and_parse(pdf_url: str, filename: str, output_dir: str, s3_key: str = "") -> None:
        captured["pdf_url"] = pdf_url
        captured["filename"] = filename
        captured["output_dir"] = output_dir
        (tmp_path / "output" / "full.md").write_text("# parsed", encoding="utf-8")

    def fake_parse_md(
        output_dir: str,
        source_type: str,
        file_path: str,
        base_llm_paras: dict[str, Any],
        relative_root: Optional[str] = None,
    ) -> dict[str, Any]:
        captured["parse_md_output_dir"] = output_dir
        captured["parse_md_file_path"] = file_path
        captured["base_llm_paras"] = dict(base_llm_paras)
        captured["relative_root"] = relative_root
        return {"ok": True}

    monkeypatch.setattr(pdf_parser, "upload_and_parse", fake_upload_and_parse)
    monkeypatch.setattr(pdf_parser, "parse_md", fake_parse_md)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    base_llm_paras = {"foo": "bar"}

    result = pdf_parser.parse_pdfs(
        str(tmp_path / "sample.pdf"),
        filename="sample.pdf",
        output_dir=str(output_dir),
        base_llm_paras=base_llm_paras,
        profile=None,
        relative_root="root",
    )

    assert result == {"ok": True}
    assert captured["pdf_url"].endswith("sample.pdf")
    assert captured["filename"] == "sample.pdf"
    assert captured["output_dir"] == str(output_dir)
    assert captured["parse_md_output_dir"] == str(output_dir)
    assert captured["parse_md_file_path"] == str(output_dir / "full.md")
    assert captured["base_llm_paras"]["doc_name"] == "sample.pdf"
    assert captured["relative_root"] == "root"


def test_local_upload_network_errors_raise_mineru_service_exception(
    monkeypatch, tmp_path
):
    local_pdf_path = tmp_path / "sample.pdf"
    local_pdf_path.write_bytes(b"%PDF-1.4\n")

    def fake_put(url: str, data: Any = None, timeout: Any = None) -> None:
        assert url == "https://mineru-upload.example/file"
        assert timeout == mineru_pdf_service.MINERU_UPLOAD_TIMEOUT
        raise mineru_pdf_service.requests.exceptions.ConnectTimeout("connect timed out")

    monkeypatch.setattr(mineru_pdf_service.requests, "put", fake_put)

    with pytest.raises(MinerUServiceException) as exc_info:
        mineru_pdf_service._upload_file_to_mineru(
            str(local_pdf_path),
            "sample.pdf",
            "https://mineru-upload.example/file",
            "token-1",
        )

    assert "Failed to upload file to MinerU" in exc_info.value.internal_message
