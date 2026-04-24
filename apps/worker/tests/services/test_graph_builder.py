"""
Unit tests for graph_builder module.
"""

import os
import tempfile

from app.services.connect_builder.graph_builder import (
    _build_tree_from_paths,
    _chunks_to_nodes,
    _connections_to_edges,
    _incremental_connections,
    _merge_tree,
    build_knowledge_graph,
    extract_chunks_from_graph,
    load_knowledge_graph,
    save_knowledge_graph,
    update_knowledge_graph,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_chunk(chunk_id: str, path: str, keywords: list, content: str = "") -> dict:
    """Create a chunk dict matching ChunksRedisService format."""
    return {
        "chunk_id": chunk_id,
        "type": "text",
        "content": content or f"Content of {chunk_id}",
        "path": path,
        "metadata": {
            "keywords": keywords,
            "summary": f"Summary of {chunk_id}",
        },
    }


# ─── Test: _build_tree_from_paths ────────────────────────────────────────────


class TestBuildTreeFromPaths:
    def test_single_file(self):
        paths = [
            "Default_Root/report.pdf/Chapter1/Section1",
            "Default_Root/report.pdf/Chapter1/Section2",
            "Default_Root/report.pdf/Chapter2",
        ]
        tree = _build_tree_from_paths(paths)
        assert "Default_Root" in tree
        assert "report.pdf" in tree["Default_Root"]
        assert "Chapter1" in tree["Default_Root"]["report.pdf"]
        assert "Section1" in tree["Default_Root"]["report.pdf"]["Chapter1"]
        assert "Section2" in tree["Default_Root"]["report.pdf"]["Chapter1"]
        assert "Chapter2" in tree["Default_Root"]["report.pdf"]

    def test_multiple_files(self):
        paths = [
            "Default_Root/a.pdf/Ch1",
            "Default_Root/b.docx/Sec1",
        ]
        tree = _build_tree_from_paths(paths)
        root = tree["Default_Root"]
        assert "a.pdf" in root
        assert "b.docx" in root

    def test_empty_paths(self):
        assert _build_tree_from_paths([]) == {}
        assert _build_tree_from_paths(["", None]) == {}

    def test_legacy_separator(self):
        paths = ["Default_Root-->report.pdf-->Chapter1"]
        tree = _build_tree_from_paths(paths)
        assert "Default_Root" in tree
        assert "report.pdf" in tree["Default_Root"]


# ─── Test: _merge_tree ───────────────────────────────────────────────────────


class TestMergeTree:
    def test_disjoint_trees(self):
        base = {"Default_Root": {"a.pdf": {"Ch1": {}}}}
        add = {"Default_Root": {"b.docx": {"Sec1": {}}}}
        _merge_tree(base, add)
        assert "a.pdf" in base["Default_Root"]
        assert "b.docx" in base["Default_Root"]

    def test_overlapping_keys(self):
        base = {"Default_Root": {"a.pdf": {"Ch1": {}}}}
        add = {"Default_Root": {"a.pdf": {"Ch2": {}}}}
        _merge_tree(base, add)
        assert "Ch1" in base["Default_Root"]["a.pdf"]
        assert "Ch2" in base["Default_Root"]["a.pdf"]

    def test_empty_addition(self):
        base = {"Default_Root": {"a.pdf": {}}}
        _merge_tree(base, {})
        assert "a.pdf" in base["Default_Root"]


# ─── Test: _chunks_to_nodes ──────────────────────────────────────────────────


class TestChunksToNodes:
    def test_basic_extraction(self):
        chunks = [_make_chunk("c1", "Root/a.pdf/Ch1", ["PPO", "RL"])]
        nodes = _chunks_to_nodes(chunks)
        assert len(nodes) == 1
        assert nodes[0]["id"] == "c1"
        assert nodes[0]["keywords"] == ["PPO", "RL"]
        assert nodes[0]["path"] == "Root/a.pdf/Ch1"

    def test_content_preview_truncation(self):
        chunks = [_make_chunk("c1", "Root/a.pdf/Ch1", [], content="A" * 500)]
        nodes = _chunks_to_nodes(chunks, content_preview_len=100)
        assert len(nodes[0]["content_preview"]) == 100

    def test_empty_chunks(self):
        assert _chunks_to_nodes([]) == []


# ─── Test: _connections_to_edges ─────────────────────────────────────────────


class TestConnectionsToEdges:
    def test_deduplication(self):
        """Bidirectional connections should produce one edge."""
        connections = {
            "c1": [
                {
                    "target": "c2",
                    "relation": "related",
                    "score": 0.8,
                    "keywords": ["ppo"],
                }
            ],
            "c2": [
                {
                    "target": "c1",
                    "relation": "related",
                    "score": 0.8,
                    "keywords": ["ppo"],
                }
            ],
        }
        edges = _connections_to_edges(connections)
        assert len(edges) == 1  # Deduplicated

    def test_empty(self):
        assert _connections_to_edges({}) == []


# ─── Test: build_knowledge_graph ─────────────────────────────────────────────


class TestBuildKnowledgeGraph:
    def test_basic_graph(self):
        chunks = [
            _make_chunk("c1", "Default_Root/a.pdf/Ch1", ["PPO", "RL"]),
            _make_chunk("c2", "Default_Root/b.pdf/Sec1", ["PPO", "DQN"]),
        ]
        connections = {
            "c1": [
                {
                    "target": "c2",
                    "relation": "related",
                    "score": 0.85,
                    "keywords": ["ppo"],
                }
            ],
            "c2": [
                {
                    "target": "c1",
                    "relation": "related",
                    "score": 0.85,
                    "keywords": ["ppo"],
                }
            ],
        }
        graph = build_knowledge_graph(chunks, connections, kb_id="test_kb")

        assert graph["version"] == "2.0"
        assert graph["kb_id"] == "test_kb"
        assert graph["stats"]["total_files"] == 2
        assert graph["stats"]["total_chunks"] == 2
        assert graph["stats"]["total_cross_file_edges"] == 1
        assert "files" in graph
        assert len(graph["files"]) == 2
        # Each file should have top_keywords
        for fk, finfo in graph["files"].items():
            assert "top_keywords" in finfo
            assert "chunks_count" in finfo
            assert finfo["chunks_count"] == 1

    def test_no_edges_valid_graph(self):
        """Graph with no connections is still valid."""
        chunks = [
            _make_chunk("c1", "Default_Root/a.pdf/Ch1", ["PPO"]),
            _make_chunk("c2", "Default_Root/a.pdf/Ch2", ["DQN"]),
        ]
        graph = build_knowledge_graph(chunks, {}, kb_id="tree_only")

        assert graph["stats"]["total_files"] == 1  # Same file
        assert graph["stats"]["total_chunks"] == 2
        assert graph["stats"]["total_cross_file_edges"] == 0

    def test_empty_input(self):
        graph = build_knowledge_graph([], {})
        assert graph["stats"]["total_files"] == 0
        assert graph["stats"]["total_chunks"] == 0
        assert graph["files"] == {}


# ─── Test: _incremental_connections ──────────────────────────────────────────


class TestIncrementalConnections:
    def test_new_matches_existing(self):
        """New chunks with shared keywords should connect to existing."""
        existing = [
            _make_chunk(
                "e1",
                "Root/doc1.pdf/Sec1",
                ["施工方案", "基坑", "支护", "钢筋", "混凝土"],
            ),
        ]
        new = [
            _make_chunk(
                "n1", "Root/doc2.pdf/Ch1", ["施工方案", "基坑", "安全", "交底", "支护"]
            ),
        ]
        config = {
            "min_keyword_overlap": 2,
            "min_score_threshold": 0.1,
            "max_content_overlap": 1.0,
        }
        conns = _incremental_connections(new, existing, config)

        assert len(conns) > 0
        # Should have bidirectional
        all_targets = []
        for conn_list in conns.values():
            for c in conn_list:
                all_targets.append(c["target"])
        assert "e1" in all_targets or "n1" in all_targets

    def test_no_overlap_no_connections(self):
        """No shared keywords → no connections."""
        existing = [_make_chunk("e1", "Root/a.pdf/S1", ["alpha", "beta"])]
        new = [_make_chunk("n1", "Root/b.pdf/S1", ["gamma", "delta"])]
        conns = _incremental_connections(new, existing)
        assert len(conns) == 0

    def test_empty_inputs(self):
        assert _incremental_connections([], []) == {}
        assert (
            _incremental_connections([], [_make_chunk("e1", "R/a.pdf/S", ["a"])]) == {}
        )


# ─── Test: update_knowledge_graph ────────────────────────────────────────────


class TestUpdateKnowledgeGraph:
    def test_incremental_update(self):
        """Adding new file should expand files dict."""
        initial_chunks = [
            _make_chunk("c1", "Default_Root/a.pdf/Ch1", ["PPO", "RL"]),
        ]
        initial_graph = build_knowledge_graph(initial_chunks, {}, kb_id="kb1")
        assert initial_graph["stats"]["total_files"] == 1

        new_chunks = [
            _make_chunk("c2", "Default_Root/b.docx/Sec1", ["RL", "DQN"]),
        ]

        updated = update_knowledge_graph(
            existing_graph=initial_graph,
            new_chunks=new_chunks,
            existing_chunks=initial_chunks,
            connect_config={"min_keyword_overlap": 1, "min_score_threshold": 0.1},
        )

        assert updated["stats"]["total_files"] == 2
        assert updated["stats"]["total_chunks"] == 2

    def test_tree_merges_correctly(self):
        initial = build_knowledge_graph(
            [_make_chunk("c1", "Default_Root/a.pdf/Ch1", [])], {}, kb_id="kb"
        )
        new = [_make_chunk("c2", "Default_Root/a.pdf/Ch2", [])]
        updated = update_knowledge_graph(
            initial, new, [_make_chunk("c1", "Default_Root/a.pdf/Ch1", [])]
        )

        # Same file, chunks should be merged
        assert updated["stats"]["total_files"] == 1
        assert updated["stats"]["total_chunks"] == 2


# ─── Test: File I/O ──────────────────────────────────────────────────────────


class TestFileIO:
    def test_save_and_load(self):
        graph = build_knowledge_graph(
            [_make_chunk("c1", "Root/a.pdf/Ch1", ["test"])], {}, kb_id="io_test"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "knowledge_graph.json")
            save_knowledge_graph(graph, path)

            assert os.path.exists(path)
            loaded = load_knowledge_graph(path)
            assert loaded is not None
            assert loaded["kb_id"] == "io_test"
            assert loaded["stats"]["total_files"] == 1

    def test_load_nonexistent(self):
        assert load_knowledge_graph("/tmp/nonexistent_kg.json") is None

    def test_extract_chunks_from_graph_v2(self):
        """v2.0 graph returns empty (chunks live in files)."""
        graph = build_knowledge_graph(
            [_make_chunk("c1", "Root/a.pdf/Ch1", ["PPO"])], {}, kb_id="test"
        )
        chunks = extract_chunks_from_graph(graph)
        assert len(chunks) == 0  # v2.0: no chunk data in graph
