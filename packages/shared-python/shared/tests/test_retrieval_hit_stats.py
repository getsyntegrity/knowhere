import os
from types import SimpleNamespace

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

import shared.models.database  # noqa: F401
from shared.services.retrieval.hit_stats_service import record_retrieval_hits


async def _scalar_none():
    return None


def test_record_retrieval_hits_writes_document_and_chunk_rows():
    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Db:
        def __init__(self):
            self.added = []

        async def execute(self, _stmt):
            return _Result()

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            return None

    db = _Db()

    results = [
        {
            'document_id': 'doc_123',
            'chunk_id': 'chunk_456',
        }
    ]

    import asyncio
    asyncio.run(record_retrieval_hits(db, user_id='user_123', namespace='default', results=results))

    added = list(db.added)
    assert len(added) == 2
    hit_kinds = sorted(row.hit_kind for row in added)
    assert hit_kinds == ['chunk', 'document']


def test_record_retrieval_hits_deduplicates_document_hits():
    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Db:
        def __init__(self):
            self.added = []

        async def execute(self, _stmt):
            return _Result()

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            return None

    db = _Db()

    results = [
        {'document_id': 'doc_123', 'chunk_id': 'chunk_1'},
        {'document_id': 'doc_123', 'chunk_id': 'chunk_2'},
    ]

    import asyncio
    asyncio.run(record_retrieval_hits(db, user_id='user_123', namespace='default', results=results))

    added = list(db.added)
    document_rows = [row for row in added if row.hit_kind == 'document']
    chunk_rows = [row for row in added if row.hit_kind == 'chunk']
    assert len(document_rows) == 1
    assert len(chunk_rows) == 2


def test_record_retrieval_hits_increments_existing_rows_instead_of_appending_duplicates():
    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _Db:
        def __init__(self):
            self.added = []
            self.document_row = SimpleNamespace(
                user_id='user_123',
                namespace='default',
                hit_kind='document',
                document_id='doc_123',
                chunk_id=None,
                hit_count=3,
                last_hit_at=None,
            )
            self.chunk_row = SimpleNamespace(
                user_id='user_123',
                namespace='default',
                hit_kind='chunk',
                document_id='doc_123',
                chunk_id='chunk_456',
                hit_count=7,
                last_hit_at=None,
            )

        async def execute(self, stmt):
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            if "hit_kind = 'document'" in compiled:
                return _Result(self.document_row)
            if "hit_kind = 'chunk'" in compiled:
                return _Result(self.chunk_row)
            return _Result(None)

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            return None

    db = _Db()

    results = [
        {
            'document_id': 'doc_123',
            'chunk_id': 'chunk_456',
        }
    ]

    import asyncio
    asyncio.run(record_retrieval_hits(db, user_id='user_123', namespace='default', results=results))

    assert db.added == []
    assert db.document_row.hit_count == 4
    assert db.chunk_row.hit_count == 8
    assert db.document_row.last_hit_at is not None
    assert db.chunk_row.last_hit_at is not None
