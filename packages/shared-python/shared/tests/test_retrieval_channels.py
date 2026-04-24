import os
from pathlib import Path

import pytest

_TEST_ROOT = Path(__file__).resolve().parents[2]

os.environ.setdefault("DS_KEY", "test-key")
os.environ.setdefault("DS_URL", "https://example.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("S3_TEMP_PATH", str(_TEST_ROOT))
os.environ.setdefault("USERS_DATA_PATH", str(_TEST_ROOT))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/testdb"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TMP_PATH", str(_TEST_ROOT))
os.environ.setdefault("FONT_PATH", str(_TEST_ROOT / "shared/tests/.tmp_layout_parser/font.ttf"))
os.environ.setdefault(
    "CHROMEDRIVER_PATH", str(_TEST_ROOT / "shared/tests/.tmp_layout_parser/chromedriver")
)

from shared.services.retrieval.agent_navigate import _grep_discover_document_ids
from shared.services.retrieval.channels import content_channel, path_channel, term_channel
from shared.services.retrieval.lexical_text import (
    build_content_search_text,
    build_path_search_text,
)
from shared.utils.text_utils import tokenize_for_retrieval


class _FakeRow:
    def __init__(self, mapping):
        self._mapping = mapping


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.last_stmt = None
        self.last_params = None

    async def execute(self, stmt, params=None):
        self.last_stmt = stmt
        self.last_params = params
        if self.rows and isinstance(self.rows[0], tuple):
            return _FakeResult(self.rows)
        return _FakeResult([_FakeRow(row) for row in self.rows])


def _channel_row(
    *,
    document_id: str,
    chunk_id: str,
    content: str = "",
    content_search_text: str = "",
    path_search_text: str = "",
    term_search_text: str = "",
    section_path: str = "Root",
):
    return {
        "id": f"row_{chunk_id}",
        "chunk_id": chunk_id,
        "document_id": document_id,
        "section_id": None,
        "chunk_type": "text",
        "content": content,
        "file_path": None,
        "chunk_metadata": {},
        "job_result_id": "jr_123",
        "sort_order": 0,
        "content_search_text": content_search_text,
        "path_search_text": path_search_text,
        "term_search_text": term_search_text,
        "source_file_name": f"{document_id}.md",
        "user_id": "user_123",
        "namespace": "default",
        "section_path": section_path,
        "job_id": "job_123",
    }


def test_tokenize_for_retrieval_handles_mixed_language_and_stopwords():
    tokens = tokenize_for_retrieval("查询 the stainless-steel welding parameters 在 Section 2.1", dedupe=True)

    assert "查询" in tokens
    assert "stainless" in tokens
    assert "steel" in tokens
    assert "welding" in tokens
    assert "parameters" in tokens
    assert "the" not in tokens


def test_build_content_search_text_preserves_repeated_terms_for_bm25():
    text = build_content_search_text({"content": "welding welding parameters"})

    assert text is not None
    assert text.split().count("welding") == 2


@pytest.mark.asyncio
async def test_path_channel_ranks_path_hits_with_bm25():
    db = _FakeDB([
        _channel_row(
            document_id="doc_path_best",
            chunk_id="chunk_best",
            path_search_text=build_path_search_text(
                source_file_name="welding-guide.md",
                section_path="Manufacturing / Stainless Steel Welding Parameters",
                section_title="Welding Parameters",
                section_summary="Recommended settings for stainless steel joints",
            ) or "",
        ),
        _channel_row(
            document_id="doc_path_other",
            chunk_id="chunk_other",
            path_search_text=build_path_search_text(
                source_file_name="refund-guide.md",
                section_path="Policies / Billing / Refunds",
                section_title="Refund Policy",
                section_summary="Annual plan refund rules",
            ) or "",
        ),
    ])

    rows = await path_channel(
        db,
        user_id="user_123",
        namespace="default",
        query="stainless steel welding parameters",
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert [row["document_id"] for row in rows] == ["doc_path_best"]
    assert rows[0]["score"] != 0


@pytest.mark.asyncio
async def test_content_channel_uses_same_tokenizer_for_mixed_language_query():
    db = _FakeDB([
        _channel_row(
            document_id="doc_content_best",
            chunk_id="chunk_best",
            content="Atlas handbook welding setup",
            content_search_text=build_content_search_text(
                {"content": "Atlas handbook 提供 stainless steel welding parameters"}
            ) or "",
        ),
        _channel_row(
            document_id="doc_content_other",
            chunk_id="chunk_other",
            content="Finance refund process",
            content_search_text=build_content_search_text(
                {"content": "Annual refund policy for billing changes"}
            ) or "",
        ),
    ])

    rows = await content_channel(
        db,
        user_id="user_123",
        namespace="default",
        query="Atlas handbook 不锈钢 welding parameters",
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert [row["document_id"] for row in rows] == ["doc_content_best"]
    assert rows[0]["score"] != 0


@pytest.mark.asyncio
async def test_term_channel_ignores_english_stopwords_in_query_units():
    db = _FakeDB([
        _channel_row(
            document_id="doc_stopword_only",
            chunk_id="chunk_stopword",
            term_search_text="the the the the only stopword text",
        ),
        _channel_row(
            document_id="doc_refund",
            chunk_id="chunk_refund",
            term_search_text="refund policy for annual billing plans",
        ),
    ])

    rows = await term_channel(
        db,
        user_id="user_123",
        namespace="default",
        query="the refund policy",
        top_k=5,
        exclude_document_ids=[],
        exclude_sections=[],
    )

    assert [row["document_id"] for row in rows] == ["doc_refund"]


@pytest.mark.asyncio
async def test_grep_discovery_reuses_unified_query_tokens():
    db = _FakeDB([("doc_refund",)])

    doc_ids = await _grep_discover_document_ids(
        db,
        user_id="user_123",
        namespace="default",
        query="the refund policy",
        limit=10,
    )

    assert doc_ids == ["doc_refund"]
    compiled = db.last_stmt.compile(compile_kwargs={"literal_binds": False})
    assert "the" not in {str(value).lower() for value in compiled.params.values()}
    assert "%refund%" in {str(value).lower() for value in compiled.params.values()}
