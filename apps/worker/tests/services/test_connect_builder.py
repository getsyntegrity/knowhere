"""
Unit tests for connect_builder module.
"""
import json

from app.services.connect_builder.builder import (
    DEFAULT_CONFIG,
    build_connections,
    deserialize_connections,
    serialize_connections,
    _build_keyword_index,
    _compute_keyword_score,
    _extract_file_key,
    _normalize_keyword,
    classify_relation,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_chunk(chunk_id: str, path: str, keywords: list) -> dict:
    """Create a minimal chunk dict for testing."""
    return {
        "chunk_id": chunk_id,
        "path": path,
        "metadata": {"keywords": keywords},
    }


# ─── Test: _normalize_keyword ─────────────────────────────────────────────────

class TestNormalizeKeyword:
    def test_lowercase(self):
        assert _normalize_keyword("PPO") == "ppo"

    def test_strip_whitespace(self):
        assert _normalize_keyword("  reinforcement learning  ") == "reinforcement learning"

    def test_collapse_spaces(self):
        assert _normalize_keyword("deep   learning") == "deep learning"

    def test_empty_string(self):
        assert _normalize_keyword("") == ""


# ─── Test: _extract_file_key ──────────────────────────────────────────────────

class TestExtractFileKey:
    def test_standard_path(self):
        assert _extract_file_key("Default_Root/paper.pdf/Section 1") == "Default_Root/paper.pdf"

    def test_deep_path(self):
        assert _extract_file_key("KB_DATA/reports/annual.docx/Table 1") == "KB_DATA/reports/annual.docx"

    def test_no_extension(self):
        assert _extract_file_key("Root/folder/section") == "Root/folder/section"

    def test_empty(self):
        assert _extract_file_key("") == ""


# ─── Test: _compute_keyword_score ─────────────────────────────────────────────

class TestComputeKeywordScore:
    def test_full_overlap(self):
        # 3 shared out of min(3, 5) = 3 → 1.0
        assert _compute_keyword_score(3, 3, 5) == 1.0

    def test_partial_overlap(self):
        # 2 shared out of min(4, 6) = 4 → 0.5
        assert _compute_keyword_score(2, 4, 6) == 0.5

    def test_zero_denominator(self):
        assert _compute_keyword_score(0, 0, 5) == 0.0

    def test_weight(self):
        # 2/4 * 2.0 = 1.0
        assert _compute_keyword_score(2, 4, 6, weight=2.0) == 1.0

    def test_linear_scaling(self):
        # 1/3 ≈ 0.333, 2/3 ≈ 0.667, 3/3 = 1.0 → linear
        s1 = _compute_keyword_score(1, 3, 5)
        s2 = _compute_keyword_score(2, 3, 5)
        s3 = _compute_keyword_score(3, 3, 5)
        assert s1 < s2 < s3
        assert abs(s2 - s1 - (s3 - s2)) < 0.001  # equal increments


# ─── Test: _build_keyword_index ───────────────────────────────────────────────

class TestBuildKeywordIndex:
    def test_basic_index(self):
        chunks = [
            _make_chunk("c1", "Root/a.pdf/sec1", ["PPO", "RL"]),
            _make_chunk("c2", "Root/b.pdf/sec1", ["PPO", "DQN"]),
        ]
        idx = _build_keyword_index(chunks)
        assert "ppo" in idx
        assert len(idx["ppo"]) == 2
        assert "rl" in idx
        assert "dqn" in idx

    def test_empty_keywords_skipped(self):
        chunks = [_make_chunk("c1", "Root/a.pdf/sec1", [])]
        idx = _build_keyword_index(chunks)
        assert len(idx) == 0

    def test_keyword_string_format(self):
        """Test chunks with semicolon-separated keyword string."""
        chunk = {"chunk_id": "c1", "path": "Root/a.pdf/sec", "keywords": "PPO;RL;DQN"}
        idx = _build_keyword_index([chunk])
        assert "ppo" in idx
        assert "rl" in idx
        assert "dqn" in idx


# ─── Test: build_connections ──────────────────────────────────────────────────

class TestBuildConnections:
    def test_cross_file_match(self):
        """Chunks from different files with shared keywords should connect."""
        chunks = [
            _make_chunk("c1", "Root/paper_a.pdf/method", ["PPO", "RL", "Atari"]),
            _make_chunk("c2", "Root/paper_b.pdf/method", ["PPO", "RL", "MuJoCo"]),
        ]
        config = {"min_keyword_overlap": 2, "min_score_threshold": 0.1}
        conns = build_connections(chunks, config)

        assert "c1" in conns
        assert len(conns["c1"]) == 1
        assert conns["c1"][0]["target"] == "c2"
        assert conns["c1"][0]["relation"] == "related"
        assert set(conns["c1"][0]["keywords"]) == {"ppo", "rl"}

        # Bidirectional
        assert "c2" in conns
        assert conns["c2"][0]["target"] == "c1"

    def test_same_file_not_connected(self):
        """cross_file_only=True should skip same-file chunks."""
        chunks = [
            _make_chunk("c1", "Root/paper.pdf/sec1", ["PPO", "RL"]),
            _make_chunk("c2", "Root/paper.pdf/sec2", ["PPO", "RL"]),
        ]
        config = {"cross_file_only": True, "min_keyword_overlap": 1, "min_score_threshold": 0.1}
        conns = build_connections(chunks, config)
        assert len(conns) == 0

    def test_same_file_connected_when_disabled(self):
        """cross_file_only=False should allow same-file connections."""
        chunks = [
            _make_chunk("c1", "Root/paper.pdf/sec1", ["PPO", "RL"]),
            _make_chunk("c2", "Root/paper.pdf/sec2", ["PPO", "RL"]),
        ]
        config = {"cross_file_only": False, "min_keyword_overlap": 1, "min_score_threshold": 0.1}
        conns = build_connections(chunks, config)
        assert "c1" in conns

    def test_below_threshold_excluded(self):
        """Score below threshold should not produce connections."""
        chunks = [
            _make_chunk("c1", "Root/a.pdf/sec1", ["PPO", "RL", "MCTS", "AlphaGo", "GPT"]),
            _make_chunk("c2", "Root/b.pdf/sec1", ["PPO", "TensorFlow", "Keras", "NumPy", "PyTorch"]),
        ]
        # Only 1 shared keyword out of 5 = score 0.2, threshold 0.5 → excluded
        config = {"min_keyword_overlap": 1, "min_score_threshold": 0.5}
        conns = build_connections(chunks, config)
        assert len(conns) == 0

    def test_below_min_overlap_excluded(self):
        """Fewer shared keywords than min_keyword_overlap → excluded."""
        chunks = [
            _make_chunk("c1", "Root/a.pdf/sec1", ["PPO", "RL"]),
            _make_chunk("c2", "Root/b.pdf/sec1", ["PPO", "DQN"]),
        ]
        config = {"min_keyword_overlap": 2, "min_score_threshold": 0.1}
        conns = build_connections(chunks, config)
        assert len(conns) == 0

    def test_empty_keywords_no_error(self):
        """Chunks with no keywords should not cause errors."""
        chunks = [
            _make_chunk("c1", "Root/a.pdf/sec1", []),
            _make_chunk("c2", "Root/b.pdf/sec1", ["PPO"]),
        ]
        conns = build_connections(chunks)
        assert len(conns) == 0

    def test_max_connections(self):
        """Should limit to max_connections_per_chunk."""
        # Create many matching chunks
        chunks = [_make_chunk("c0", "Root/a.pdf/sec", ["PPO", "RL"])]
        for i in range(1, 20):
            chunks.append(_make_chunk(f"c{i}", f"Root/paper_{i}.pdf/sec", ["PPO", "RL"]))

        config = {
            "min_keyword_overlap": 1,
            "min_score_threshold": 0.1,
            "max_connections_per_chunk": 5,
        }
        conns = build_connections(chunks, config)
        for cid, conn_list in conns.items():
            assert len(conn_list) <= 5


# ─── Test: Serialization ─────────────────────────────────────────────────────

class TestSerialization:
    def test_roundtrip(self):
        connections = [
            {"target": "abc123", "relation": "related", "score": 0.85, "keywords": ["ppo", "rl"]},
        ]
        serialized = serialize_connections(connections)
        deserialized = deserialize_connections(serialized)

        assert len(deserialized) == 1
        assert deserialized[0]["target"] == "abc123"
        assert deserialized[0]["score"] == 0.85

    def test_serialize_empty(self):
        assert serialize_connections([]) == ""

    def test_deserialize_none(self):
        assert deserialize_connections(None) == []

    def test_deserialize_empty_string(self):
        assert deserialize_connections("") == []

    def test_deserialize_legacy_newline(self):
        result = deserialize_connections("chunk1\nchunk2")
        assert len(result) == 2
        assert result[0]["target"] == "chunk1"
        assert result[1]["target"] == "chunk2"

    def test_deserialize_legacy_single(self):
        result = deserialize_connections("chunk_abc")
        assert len(result) == 1
        assert result[0]["target"] == "chunk_abc"

    def test_valid_json_output(self):
        """Serialized output should be valid JSON."""
        connections = [
            {"target": "id1", "relation": "related", "score": 0.5, "keywords": ["a"]},
            {"target": "id2", "relation": "related", "score": 0.7, "keywords": ["b"]},
        ]
        serialized = serialize_connections(connections)
        parsed = json.loads(serialized)
        assert len(parsed) == 2


# ─── Test: classify_relation (stub) ──────────────────────────────────────────

class TestClassifyRelation:
    def test_stub_returns_related(self):
        result = classify_relation("summary A", "summary B", ["ppo"])
        assert result["relation"] == "related"
        assert result["confidence"] == 1.0
        assert "ppo" in result["reason"]
