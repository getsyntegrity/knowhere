import pytest


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
        graph_enabled=False,
        response={'namespace': 'default', 'query': 'refund policy', 'results': [], 'graph_enabled': False},
    )

    _, same_shape = await cache_service.get_cached_retrieval_query_result(
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=5,
        exclude_document_ids=[],
        graph_enabled=False,
    )
    _, different_shape = await cache_service.get_cached_retrieval_query_result(
        user_id='user_123',
        namespace='default',
        query='refund policy',
        top_k=10,
        exclude_document_ids=[],
        graph_enabled=False,
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
        graph_enabled=False,
        response={'namespace': 'default', 'query': 'refund policy', 'results': [], 'graph_enabled': False},
    )

    assert any(':v7:' in key for key in fake_redis.values.keys())
