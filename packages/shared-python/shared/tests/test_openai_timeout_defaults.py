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
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/testdb"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TMP_PATH", "/tmp")
os.environ.setdefault("FONT_PATH", "/tmp/font.ttf")
os.environ.setdefault("CHROMEDRIVER_PATH", "/tmp/chromedriver")

import shared.utils.ali_quota_manager as ali_quota_manager_module
import shared.utils.OpenAICompatibleClientSync as openai_client_sync_module
from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import LLMServiceException
from shared.services.ai.prompt_service import build_prompt
from shared.services.ai.response_process_service import eval_response
from shared.utils.OpenAICompatibleClientSync import OpenAICompatibleClientSync
from shared.utils.security_utils import mask_api_key


@pytest.fixture(autouse=True)
def disable_llm_mock_by_default(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MOCK_ENABLED", False, raising=False)


def test_openai_compatible_client_uses_config_timeout_by_default(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_CLIENT_TIMEOUT", 300, raising=False)

    sync_client = OpenAICompatibleClientSync()

    assert sync_client.timeout == 300


def test_openai_compatible_client_allows_timeout_override():
    sync_client = OpenAICompatibleClientSync(timeout=180)

    assert sync_client.timeout == 180


def test_openai_compatible_client_skips_direct_client_for_qwen_pool(monkeypatch):
    def fail_openai(**kwargs: Any) -> None:
        raise AssertionError(
            "Qwen pool mode should not build a direct OpenAI client during __init__"
        )

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


def test_openai_compatible_client_builds_direct_qwen_client_for_explicit_key(
    monkeypatch,
):
    captured_api_key: str = ""
    captured_base_url: str = ""
    explicit_api_key = "ali-explicit-placeholder-key"

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
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: None)
            )

    monkeypatch.setattr(openai_client_sync_module, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_client_sync_module, "get_sync_client", lambda: object())
    monkeypatch.setattr(
        settings,
        "ALI_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        raising=False,
    )

    sync_client = OpenAICompatibleClientSync(
        default_model="qwen-vl-plus",
        api_key=explicit_api_key,
    )

    assert sync_client._client is not None
    assert captured_api_key == explicit_api_key
    assert captured_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_ali_pool_errors_include_masked_api_key_in_internal_message(monkeypatch):
    pool_api_key = "ali-pool-placeholder-key-123456"

    class FakeAliQuotaManager:
        def acquire_request(self, operation: str) -> SimpleNamespace:
            assert operation == "chat_completion"
            return SimpleNamespace(
                token_id="ali-2",
                api_key=pool_api_key,
                rpm_limit=300,
                daily_limit=10000,
            )

        def mark_rate_limited(
            self, token_id: str, retry_after: int | None = None
        ) -> None:
            raise AssertionError("Non-rate-limit errors should not trigger cooldown")

    class FakeCompletions:
        def create(self, **kwargs: Any) -> None:
            raise RuntimeError("Error code: 400 - arrearage")

    class FakeOpenAIClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(
        ali_quota_manager_module,
        "get_ali_quota_manager",
        lambda: FakeAliQuotaManager(),
    )

    def fake_build_client(
        self: OpenAICompatibleClientSync,
        api_key: str | None,
        base_url: str | None,
        max_retries: int,
    ) -> FakeOpenAIClient:
        assert api_key == pool_api_key
        assert max_retries == settings.ALI_SDK_MAX_RETRIES
        return FakeOpenAIClient(base_url or "")

    monkeypatch.setattr(
        OpenAICompatibleClientSync,
        "_build_client",
        fake_build_client,
    )
    monkeypatch.setattr(
        settings,
        "ALI_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        raising=False,
    )

    sync_client = OpenAICompatibleClientSync(default_model="qwen-vl-plus")

    with pytest.raises(LLMServiceException) as exc_info:
        sync_client.chat_completion("hello")

    internal_message = exc_info.value.internal_message
    expected_masked_api_key = mask_api_key(pool_api_key)
    assert "token_id=ali-2" in internal_message
    assert f"api_key={expected_masked_api_key}" in internal_message
    assert pool_api_key not in internal_message


def test_openai_compatible_client_mock_short_circuits_direct_provider(monkeypatch):
    def fail_openai(**kwargs: Any) -> None:
        raise AssertionError("Mock mode should not build a direct OpenAI client")

    monkeypatch.setattr(settings, "LLM_MOCK_ENABLED", True, raising=False)
    monkeypatch.setattr(openai_client_sync_module, "OpenAI", fail_openai)

    sync_client = OpenAICompatibleClientSync(default_model="deepseek-chat")

    response = sync_client.chat_completion(
        messages=[
            {
                "role": "user",
                "content": "Generate a concise title. Return ONLY the title.",
            }
        ],
    )

    assert sync_client._client is None
    assert response == "Mock Fragment Title"


def test_openai_compatible_client_mock_short_circuits_ali_pool(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MOCK_ENABLED", True, raising=False)

    def fail_pool_call(
        self: OpenAICompatibleClientSync,
        model: str,
        all_messages: list[Any],
        temperature: float,
        max_tokens: int,
        api_kwargs: dict[str, Any],
    ) -> str:
        raise AssertionError("Mock mode should not call the Ali token pool")

    monkeypatch.setattr(
        OpenAICompatibleClientSync, "_make_ali_pool_call", fail_pool_call
    )

    sync_client = OpenAICompatibleClientSync(default_model="qwen-vl-plus")
    prompt, _, _, _ = build_prompt(
        task="detect-table-headers",
        texts="<table><tr><td>header</td></tr></table>",
        query="",
        paras={},
    )

    response = sync_client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model="qwen-vl-plus",
    )

    assert eval_response(response) == {"answer": [0]}


def test_openai_compatible_client_mock_returns_structured_summary_payload(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MOCK_ENABLED", True, raising=False)

    sync_client = OpenAICompatibleClientSync(default_model="deepseek-chat")
    prompt, _, _, max_tokens = build_prompt(
        task="summary-full",
        texts="Example content",
        query="",
        paras={"max_tokens": 120, "kw_num": 3},
    )

    response = sync_client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )

    assert eval_response(response) == {
        "title": "Mock Title",
        "keywords": "mock",
        "summary": "Mock summary",
    }
