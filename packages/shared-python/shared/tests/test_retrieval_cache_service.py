import os

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


@pytest.mark.asyncio
async def test_bump_namespace_version_increments_and_read_uses_latest_value(monkeypatch):
    from shared.services.retrieval import cache_service

    class FakeRedis:
        def __init__(self):
            self.values = {}

        async def get(self, key, default=None):
            return self.values.get(key, default)

        async def set(self, key, value, ex=None, ttl=None):
            self.values[key] = value
            return True

        async def incr(self, key):
            next_value = int(self.values.get(key, 0)) + 1
            self.values[key] = next_value
            return next_value

    fake_redis = FakeRedis()
    monkeypatch.setattr(cache_service, 'RedisServiceFactory', type('Factory', (), {'get_service': staticmethod(lambda: fake_redis)}))

    version_1 = await cache_service.bump_retrieval_namespace_cache_version(user_id='user_123', namespace='default')
    version_2 = await cache_service.bump_retrieval_namespace_cache_version(user_id='user_123', namespace='default')
    latest = await cache_service.get_retrieval_namespace_cache_version(user_id='user_123', namespace='default')

    assert version_1 == 1
    assert version_2 == 2
    assert latest == 2


@pytest.mark.asyncio
async def test_cache_key_scope_changes_with_query_shape(monkeypatch):
    from shared.services.retrieval import cache_service

    class FakeRedis:
        def __init__(self):
            self.values = {}

        async def get(self, key, default=None):
            return self.values.get(key, default)

        async def set(self, key, value, ex=None, ttl=None):
            self.values[key] = value
            return True

    fake_redis = FakeRedis()
    monkeypatch.setattr(cache_service, 'RedisServiceFactory', type('Factory', (), {'get_service': staticmethod(lambda: fake_redis)}))

    await cache_service.set_cached_retrieval_query_result(
        user_id='user_123',
        namespace='default',
        version=0,
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
        response={'namespace': 'default', 'query': 'refund policy', 'results': []},
    )

    _, same_shape = await cache_service.get_cached_retrieval_query_result(
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )
    _, different_shape = await cache_service.get_cached_retrieval_query_result(
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=10,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert same_shape is not None
    assert different_shape is None


@pytest.mark.asyncio
async def test_set_cached_retrieval_query_result_uses_pinned_version(monkeypatch):
    from shared.services.retrieval import cache_service

    class FakeRedis:
        def __init__(self):
            self.values = {}

        async def get(self, key, default=None):
            return self.values.get(key, default)

        async def set(self, key, value, ex=None, ttl=None):
            self.values[key] = value
            return True

        async def incr(self, key):
            next_value = int(self.values.get(key, 0)) + 1
            self.values[key] = next_value
            return next_value

    fake_redis = FakeRedis()
    monkeypatch.setattr(cache_service, 'RedisServiceFactory', type('Factory', (), {'get_service': staticmethod(lambda: fake_redis)}))

    await cache_service.set_cached_retrieval_query_result(
        user_id='user_123',
        namespace='default',
        version=7,
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
        response={'namespace': 'default', 'query': 'refund policy', 'results': []},
    )

    assert any(':v7:' in key for key in fake_redis.values.keys())


def test_cache_shape_digest_changes_with_section_exclusions():
    from shared.services.retrieval.cache_service import _cache_shape_digest

    baseline = _cache_shape_digest(
        query='refund policy',
        top_k=5,
        exclude_document_ids=['doc_skip'],
        exclude_sections=[],
    )
    changed = _cache_shape_digest(
        query='refund policy',
        top_k=5,
        exclude_document_ids=['doc_skip'],
        exclude_sections=[{'document_id': 'doc_123', 'section_path': 'Policies / Billing'}],
    )

    assert baseline != changed
