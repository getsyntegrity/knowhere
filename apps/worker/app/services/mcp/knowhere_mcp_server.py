#!/usr/bin/env python3
"""
Knowhere MCP Server — Expose knowledge graph search to AI agents.

A lightweight MCP (Model Context Protocol) server that reads from
~/.knowhere/ and exposes tools for knowledge retrieval.

Usage (stdio mode, for Cursor/Claude Code/Antigravity MCP config):
    python knowhere_mcp_server.py

The server exposes 2 tools:
  - search_knowledge(query, top_k) — keyword search over chunks
  - get_knowledge_overview()        — return KB structure and stats
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─── Configuration ────────────────────────────────────────────────────────────

KNOWHERE_HOME = os.environ.get(
    "KNOWHERE_HOME",
    os.path.expanduser("~/.knowhere"),
)
KNOWLEDGE_DIR = KNOWHERE_HOME

# ─── Data Loading ─────────────────────────────────────────────────────────────


def _discover_knowledge_bases() -> Dict[str, str]:
    """
    Discover all knowledge bases under KNOWLEDGE_DIR.

    Returns:
        Dict mapping kb_id → path to knowledge_graph.json
    """
    kbs = {}
    if not os.path.isdir(KNOWLEDGE_DIR):
        return kbs
    for entry in os.listdir(KNOWLEDGE_DIR):
        kb_path = os.path.join(KNOWLEDGE_DIR, entry)
        kg_file = os.path.join(kb_path, "knowledge_graph.json")
        if os.path.isdir(kb_path) and os.path.isfile(kg_file):
            kbs[entry] = kg_file
    return kbs


def _load_graph(path: str) -> Optional[Dict[str, Any]]:
    """Load a knowledge graph JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _load_chunks_for_kb(kb_dir: str) -> List[Dict[str, Any]]:
    """
    Load full chunks data for a knowledge base.
    Searches for chunks.json files under the KB directory.
    """
    all_chunks = []
    for root, dirs, files in os.walk(kb_dir):
        for fname in files:
            if fname == "chunks.json":
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "chunks" in data:
                        all_chunks.extend(data["chunks"])
                    elif isinstance(data, list):
                        all_chunks.extend(data)
                except (json.JSONDecodeError, IOError):
                    continue
    return all_chunks


# ─── MVP Keyword Search ──────────────────────────────────────────────────────

def _tokenize_query(query: str) -> set:
    """
    Simple tokenization for search queries.
    Uses jieba if available, otherwise splits on whitespace/punctuation.
    """
    try:
        import jieba
        return set(w for w in jieba.cut(query) if len(w) > 1)
    except ImportError:
        # Fallback: split on whitespace and common punctuation
        tokens = re.split(r'[\s,;，；。！？、\-/]+', query)
        return set(t for t in tokens if len(t) > 1)


def _search_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    graph: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    MVP keyword search over chunks.

    Scoring: count of query terms found in content + keyword intersection.

    Args:
        query: User's search query.
        chunks: Full chunks data.
        graph: Knowledge graph (for retrieving related chunks).
        top_k: Maximum results to return.

    Returns:
        List of result dicts: {chunk_id, path, score, content_preview, related}.
    """
    query_terms = _tokenize_query(query)
    if not query_terms:
        return []

    # Build edge lookup from graph
    edge_map: Dict[str, List[Dict]] = {}
    if graph:
        for edge in graph.get("edges", []):
            src, tgt = edge.get("source", ""), edge.get("target", "")
            if src:
                edge_map.setdefault(src, []).append(edge)
            if tgt:
                edge_map.setdefault(tgt, []).append(edge)

    scored = []
    for chunk in chunks:
        content = chunk.get("content", "")
        metadata = chunk.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        keywords = set(metadata.get("keywords", []))
        summary = metadata.get("summary", "")

        # Score: query term hits in content + keyword intersection
        content_hits = sum(1 for t in query_terms if t in content)
        summary_hits = sum(1 for t in query_terms if t in summary)
        keyword_hits = len(query_terms & keywords)
        score = content_hits + summary_hits * 0.5 + keyword_hits * 2

        if score > 0:
            chunk_id = str(chunk.get("chunk_id") or chunk.get("know_id", ""))
            scored.append((score, chunk_id, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, chunk_id, chunk in scored[:top_k]:
        content = chunk.get("content", "")
        result = {
            "chunk_id": chunk_id,
            "path": chunk.get("path", ""),
            "score": round(score, 2),
            "content_preview": content[:500],
            "keywords": chunk.get("metadata", {}).get("keywords", []),
        }

        # Attach related chunks from graph
        related = edge_map.get(chunk_id, [])
        if related:
            result["related"] = [
                {
                    "target": e.get("target") if e.get("source") == chunk_id else e.get("source"),
                    "relation": e.get("relation", "related"),
                    "score": e.get("score", 0),
                }
                for e in related[:3]
            ]

        results.append(result)

    return results


# ─── MCP Server ──────────────────────────────────────────────────────────────

def _format_files_overview(files: Dict[str, Any], edges: List[Dict] = None) -> str:
    """Format v2.0 files dict as human-readable overview."""
    lines = []
    for fname, info in files.items():
        types = info.get('types', {})
        type_str = ', '.join(f'{t}:{n}' for t, n in types.items())
        kws = ', '.join(info.get('top_keywords', [])[:6])
        imp = info.get('importance', 0)
        lines.append(f"📄 {fname}")
        lines.append(f"   chunks: {info.get('chunks_count', 0)} ({type_str})")
        lines.append(f"   keywords: {kws}")
        lines.append(f"   importance: {imp}")
    if edges:
        lines.append("")
        lines.append("🔗 Cross-file connections:")
        for e in edges:
            lines.append(f"   {e['source']} ↔ {e['target']} ({e.get('connection_count', 0)} connections)")
    return '\n'.join(lines)


def create_server():
    """Create and configure the MCP server."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print(
            "Error: mcp package not installed. Install with:\n"
            "  pip install mcp\n"
            "Or: pip install 'mcp[cli]'",
            file=sys.stderr,
        )
        sys.exit(1)

    mcp = FastMCP(
        "knowhere",
        description="Knowledge graph search and retrieval from Knowhere parsed documents",
    )

    @mcp.tool()
    def search_knowledge(query: str, top_k: int = 5) -> str:
        """搜索知识库，返回最相关的文档片段及其关联关系。
        当用户询问问题、需要参考资料、写作或需要知识库信息时调用此工具。

        Args:
            query: 搜索查询词
            top_k: 返回结果数量 (默认5)
        """
        kbs = _discover_knowledge_bases()
        if not kbs:
            return json.dumps({
                "status": "no_knowledge_base",
                "message": f"未找到知识库。请确保已通过 Knowhere 解析文档。数据目录: {KNOWLEDGE_DIR}",
            }, ensure_ascii=False)

        all_results = []
        for kb_id, kg_path in kbs.items():
            graph = _load_graph(kg_path)
            kb_dir = os.path.dirname(kg_path)
            chunks = _load_chunks_for_kb(kb_dir)
            results = _search_chunks(query, chunks, graph, top_k)
            for r in results:
                r["kb_id"] = kb_id
            all_results.extend(results)

        # Sort across all KBs, keep top_k
        all_results.sort(key=lambda x: x["score"], reverse=True)
        all_results = all_results[:top_k]

        # Record chunk usage stats
        try:
            # Group hits by kb_id
            hits_by_kb: Dict[str, list] = {}
            for r in all_results:
                hits_by_kb.setdefault(r["kb_id"], []).append(r["chunk_id"])
            # Add project path for import
            import sys as _sys
            _proj = os.path.join(os.path.dirname(__file__), "..", "..", "..")
            if _proj not in _sys.path:
                _sys.path.insert(0, _proj)
            from app.services.connect_builder.graph_builder import record_chunk_hits
            for kid, cids in hits_by_kb.items():
                record_chunk_hits(kid, cids)
        except Exception:
            pass  # Non-critical

        return json.dumps({
            "status": "ok",
            "query": query,
            "results_count": len(all_results),
            "results": all_results,
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    def get_knowledge_overview() -> str:
        """获取知识库的整体结构概览（文件列表、关键词、重要性、跨文件关联）。
        当用户问"我有什么资料"、"知识库里有什么"或需要了解知识库全貌时调用。
        """
        kbs = _discover_knowledge_bases()
        if not kbs:
            return json.dumps({
                "status": "no_knowledge_base",
                "message": f"未找到知识库。请确保已通过 Knowhere 解析文档。数据目录: {KNOWLEDGE_DIR}",
            }, ensure_ascii=False)

        overview = {"status": "ok", "knowledge_bases": []}
        for kb_id, kg_path in kbs.items():
            graph = _load_graph(kg_path)
            if not graph:
                continue
            files = graph.get("files", {})
            edges = graph.get("edges", [])
            overview_text = _format_files_overview(files, edges)
            kb_info = {
                "kb_id": kb_id,
                "version": graph.get("version", "1.0"),
                "stats": graph.get("stats", {}),
                "updated_at": graph.get("updated_at", ""),
                "files_overview": overview_text,
            }
            overview["knowledge_bases"].append(kb_info)

        return json.dumps(overview, ensure_ascii=False, indent=2)

    return mcp


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = create_server()
    server.run()
