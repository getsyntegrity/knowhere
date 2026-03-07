import pytest

from app.services.document_parser import pdf_parser
from app.services.document_parser.mineru_quota_manager import (
    MinerUQuotaManager,
    MinerUTokenConfig,
)
from shared.core.exceptions.domain_exceptions import UnavailableException

fakeredis = pytest.importorskip("fakeredis")


class DummyRedisService:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value, ttl=None, ex=None):
        self.values[key] = value
        return True

    def eval(self, script, keys, args=None):
        raise NotImplementedError


class StubQuotaManager(MinerUQuotaManager):
    def __init__(self, token_configs, results):
        super().__init__(DummyRedisService(), token_configs)
        self.results = {
            token_id: list(outcomes)
            for token_id, outcomes in results.items()
        }

    def _reserve_token_capacity(self, token, now_ts):
        outcomes = self.results[token.token_id]
        if not outcomes:
            return False, 60, "minute"
        return outcomes.pop(0)


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


def test_parse_token_specs_supports_json_entries():
    specs = MinerUQuotaManager._parse_token_specs(
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


def test_acquire_request_skips_exhausted_token():
    manager = StubQuotaManager(
        token_configs=[
            MinerUTokenConfig(token_id="primary", api_key="sk-1", rpm_limit=300, daily_limit=10000),
            MinerUTokenConfig(token_id="backup", api_key="sk-2", rpm_limit=300, daily_limit=10000),
        ],
        results={
            "primary": [(False, 12, "minute")],
            "backup": [(True, 0, "minute")],
        },
    )

    lease = manager.acquire_request(operation="upload_url")

    assert lease.token_id == "backup"
    assert lease.api_key == "sk-2"


def test_acquire_request_reports_shortest_retry_window():
    manager = StubQuotaManager(
        token_configs=[
            MinerUTokenConfig(token_id="primary", api_key="sk-1", rpm_limit=300, daily_limit=10000),
            MinerUTokenConfig(token_id="backup", api_key="sk-2", rpm_limit=300, daily_limit=10000),
        ],
        results={
            "primary": [(False, 1800, "day")],
            "backup": [(False, 45, "minute")],
        },
    )

    try:
        manager.acquire_request(operation="poll_status")
        assert False, "Expected UnavailableException"
    except UnavailableException as exc:
        assert exc.retry_after == 45
        assert exc.period == "minute"


def test_lua_reservation_enforces_rpm_limit():
    redis_service = FakeSyncRedisService(fakeredis.FakeRedis(decode_responses=True))
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


def test_lua_reservation_respects_daily_limit(monkeypatch):
    fixed_now = 1_700_000_000
    monkeypatch.setattr(
        "app.services.document_parser.mineru_quota_manager.time.time",
        lambda: fixed_now,
    )

    redis_service = FakeSyncRedisService(fakeredis.FakeRedis(decode_responses=True))
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


def test_lua_round_robin_uses_backup_token_after_cooldown():
    fake_server = fakeredis.FakeServer()
    redis_service = FakeSyncRedisService(
        fakeredis.FakeRedis(server=fake_server, decode_responses=True)
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


def test_upload_and_parse_reuses_preferred_token_for_polling(monkeypatch, tmp_path):
    fixed_now = 1_700_000_000
    monkeypatch.setattr(
        "app.services.document_parser.mineru_quota_manager.time.time",
        lambda: fixed_now,
    )

    redis_client = fakeredis.FakeRedis(decode_responses=True)
    redis_service = FakeSyncRedisService(redis_client)
    manager = MinerUQuotaManager(
        redis_service,
        [
            MinerUTokenConfig("primary", "sk-primary", rpm_limit=10, daily_limit=100),
            MinerUTokenConfig("backup", "sk-backup", rpm_limit=10, daily_limit=100),
        ],
    )
    monkeypatch.setattr(pdf_parser, "get_mineru_quota_manager", lambda: manager)

    mineru_calls = []

    class Response:
        def __init__(self, status_code, json_data=None, text="", headers=None):
            self.status_code = status_code
            self._json_data = json_data or {}
            self.text = text
            self.headers = headers or {}

        def json(self):
            return self._json_data

    def fake_post(url, headers=None, json=None, timeout=None):
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

    def fake_put(url, data=None, timeout=None):
        mineru_calls.append(("put", url, timeout))
        return Response(200, {})

    def fake_get(url, headers=None, timeout=None):
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

    monkeypatch.setattr(pdf_parser.requests, "post", fake_post)
    monkeypatch.setattr(pdf_parser.requests, "put", fake_put)
    monkeypatch.setattr(pdf_parser.requests, "get", fake_get)
    monkeypatch.setattr(pdf_parser, "s3_download_extract_zip", fake_extract)

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
    assert mineru_calls[2] == (
        "get",
        "Bearer sk-primary",
        "https://mineru.net/api/v4/extract-results/batch/batch-1",
    )
    assert extracted["url"] == "https://mineru-results.example/full.zip"
    assert extracted["dest_dir"] == str(output_dir)

    minute_key = manager._minute_key("primary", fixed_now)
    day_key = manager._day_key("primary", fixed_now)
    assert int(redis_client.get(minute_key)) == 2
    assert int(redis_client.get(day_key)) == 2
