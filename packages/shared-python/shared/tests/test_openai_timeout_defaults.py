import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("DS_KEY", "test-key")
os.environ.setdefault("DS_URL", "https://example.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("S3_TEMP_PATH", "/tmp")
os.environ.setdefault("USERS_DATA_PATH", "/tmp")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/testdb")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TMP_PATH", "/tmp")
os.environ.setdefault("FONT_PATH", "/tmp/font.ttf")
os.environ.setdefault("CHROMEDRIVER_PATH", "/tmp/chromedriver")

import shared.utils.OpenAICompatibleClientSync as openai_client_sync_module
from shared.core.config import settings
from shared.utils.OpenAICompatibleClientSync import OpenAICompatibleClientSync


def test_openai_compatible_client_uses_config_timeout_by_default(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_CLIENT_TIMEOUT", 300, raising=False)

    sync_client = OpenAICompatibleClientSync()

    assert sync_client.timeout == 300


def test_openai_compatible_client_allows_timeout_override():
    sync_client = OpenAICompatibleClientSync(timeout=180)

    assert sync_client.timeout == 180


def test_openai_compatible_client_skips_direct_client_for_qwen_pool(monkeypatch):
    def fail_openai(**kwargs: Any) -> None:
        raise AssertionError("Qwen pool mode should not build a direct OpenAI client during __init__")

    monkeypatch.setattr(openai_client_sync_module, "OpenAI", fail_openai)
    monkeypatch.setattr(settings, "ALI_API_KEYS", "", raising=False)
    monkeypatch.setattr(
        settings,
        "ALI_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        raising=False,
    )

    sync_client = OpenAICompatibleClientSync(default_model="qwen-vl-plus")

    assert sync_client._client is None
    assert sync_client._base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_openai_compatible_client_builds_direct_qwen_client_for_explicit_key(monkeypatch):
    captured_api_key: str = ""
    captured_base_url: str = ""

    class FakeOpenAI:
        def __init__(
            self,
            *,
            api_key: str,
            base_url: str,
            http_client: Any,
            max_retries: int,
            timeout: int,
        ) -> None:
            nonlocal captured_api_key, captured_base_url
            captured_api_key = api_key
            captured_base_url = base_url
            self.base_url = base_url
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: None))

    monkeypatch.setattr(openai_client_sync_module, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_client_sync_module, "get_sync_client", lambda: object())
    monkeypatch.setattr(
        settings,
        "ALI_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        raising=False,
    )

    sync_client = OpenAICompatibleClientSync(default_model="qwen-vl-plus", api_key="sk-explicit")

    assert sync_client._client is not None
    assert captured_api_key == "sk-explicit"
    assert captured_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
