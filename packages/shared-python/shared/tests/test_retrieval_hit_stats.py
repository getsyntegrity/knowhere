import os

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

import shared.models.database  # noqa: F401
from shared.services.retrieval.hit_stats_service import record_retrieval_hits


class _Db:
    def __init__(self):
        self.statements = []
        self.params = []

    async def execute(self, stmt, params=None):
        self.statements.append(
            str(stmt.compile(compile_kwargs={"literal_binds": True}))
        )
        self.params.append(params or {})

    def add(self, _value):
        raise AssertionError("hit stats should be recorded through atomic upsert")

    async def flush(self):
        return None


def _record(results):
    import asyncio

    db = _Db()
    asyncio.run(
        record_retrieval_hits(
            db, user_id="user_123", namespace="default", results=results
        )
    )
    return db


def test_record_retrieval_hits_writes_document_and_chunk_rows():
    db = _record([{"document_id": "doc_123", "chunk_id": "chunk_456"}])

    assert len(db.statements) == 2
    assert [params["hit_kind"] for params in db.params] == ["document", "chunk"]
    assert db.params[0]["chunk_id"] is None if "chunk_id" in db.params[0] else True
    assert db.params[1]["chunk_id"] == "chunk_456"


def test_record_retrieval_hits_deduplicates_document_hits():
    db = _record(
        [
            {"document_id": "doc_123", "chunk_id": "chunk_1"},
            {"document_id": "doc_123", "chunk_id": "chunk_2"},
        ]
    )

    assert len(db.statements) == 3
    document_params = [
        params for params in db.params if params["hit_kind"] == "document"
    ]
    chunk_params = [params for params in db.params if params["hit_kind"] == "chunk"]
    assert len(document_params) == 1
    assert len(chunk_params) == 2


def test_record_retrieval_hits_uses_atomic_upsert_for_each_logical_hit():
    db = _record([{"document_id": "doc_123", "chunk_id": "chunk_456"}])

    assert len(db.statements) == 2
    assert all("ON CONFLICT" in statement for statement in db.statements)
    assert all(
        "hit_count = retrieval_hit_stats.hit_count + 1" in statement
        for statement in db.statements
    )


def test_record_retrieval_hits_handles_null_chunk_document_hits_with_partial_conflict_target():
    db = _record([{"document_id": "doc_123", "chunk_id": "chunk_456"}])

    document_statement = db.statements[0]
    chunk_statement = db.statements[1]
    assert (
        "ON CONFLICT (user_id, namespace, hit_kind, document_id)" in document_statement
    )
    assert "WHERE chunk_id IS NULL" in document_statement
    assert (
        "ON CONFLICT (user_id, namespace, hit_kind, document_id, chunk_id)"
        in chunk_statement
    )
    assert "WHERE chunk_id IS NOT NULL" in chunk_statement
