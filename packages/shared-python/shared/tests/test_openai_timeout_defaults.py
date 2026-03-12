import os

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

from shared.core.config import settings
from shared.utils.OpenAICompatibleClientSync import OpenAICompatibleClientSync


def test_openai_compatible_client_uses_config_timeout_by_default(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_CLIENT_TIMEOUT", 300, raising=False)

    sync_client = OpenAICompatibleClientSync()

    assert sync_client.timeout == 300


def test_openai_compatible_client_allows_timeout_override():
    sync_client = OpenAICompatibleClientSync(timeout=180)

    assert sync_client.timeout == 180
