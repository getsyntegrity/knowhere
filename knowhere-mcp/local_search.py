"""
Local knowledge base search for Knowhere MCP Server.

Reads from KNOWHERE_HOME (default: ~/.knowhere/) to search parsed documents
and provide knowledge base overviews.

On OpenClaw deployments, set KNOWHERE_HOME to point to the shared KB location
(e.g. ~/.openclaw/.knowhere).

Zero dependencies on worker code or connect_builder.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

from stats_tracker import record_chunk_hits


# ── Configuration ─────────────────────────────────────────────────────────────

KNOWHERE_HOME = os.path.expanduser(
    os.environ.get("KNOWHERE_HOME", "~/.knowhere")
)


# ── Data Loading ──────────────────────────────────────────────────────────────


def discover_knowledge_bases() -> Dict[str, str]:
    """Discover all knowledge bases under KNOWHERE_HOME.

    Returns:
        Dict mapping kb_id → path to knowledge_graph.json
    """
    kbs = {}
    if not os.path.isdir(KNOWHERE_HOME):
        return kbs
    for entry in os.listdir(KNOWHERE_HOME):
        kb_path = os.path.join(KNOWHERE_HOME, entry)
        kg_file = os.path.join(kb_path, "knowledge_graph.json")
        if os.path.isdir(kb_path) and os.path.isfile(kg_file):
            kbs[entry] = kg_file
    return kbs


def load_graph(path: str) -> Optional[Dict[str, Any]]:
    """Load a knowledge graph JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_chunks_for_kb(kb_dir: str) -> List[Dict[str, Any]]:
    """Load full chunks data for a knowledge base.

    Walks the KB directory and collects all chunks.json files.
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


# ── Keyword Search ────────────────────────────────────────────────────────────


def _tokenize_query(query: str) -> set:
    """Simple tokenization for search queries.

    Uses jieba if available, otherwise splits on whitespace/punctuation.
    """
    try:
        import jieba
        return set(w for w in jieba.cut(query) if len(w) > 1)
    except ImportError:
        tokens = re.split(r'[\s,;，；。！？、\-/]+', query)
        return set(t for t in tokens if len(t) > 1)


def search_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    graph: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Keyword search over chunks with KG edge context.

    Scoring: query term hits in content + keyword intersection + summary hits.

    Args:
        query: User's search query.
        chunks: Full chunks data.
        graph: Knowledge graph (for retrieving related chunks via edges).
        top_k: Maximum results to return.

    Returns:
        List of result dicts with chunk_id, path, score, content_preview, related.
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

        # Attach related chunks from graph edges
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


# ── Knowledge Overview ────────────────────────────────────────────────────────


def format_files_overview(
    files: Dict[str, Any],
    edges: Optional[List[Dict]] = None,
) -> str:
    """Format v2.0 files dict as human-readable overview."""
    lines = []
    for fname, info in files.items():
        types = info.get("types", {})
        type_str = ", ".join(f"{t}:{n}" for t, n in types.items())
        kws = ", ".join(info.get("top_keywords", [])[:6])
        imp = info.get("importance", 0)
        lines.append(f"📄 {fname}")
        lines.append(f"   chunks: {info.get('chunks_count', 0)} ({type_str})")
        lines.append(f"   keywords: {kws}")
        lines.append(f"   importance: {imp}")
    if edges:
        lines.append("")
        lines.append("🔗 Cross-file connections:")
        for e in edges:
            lines.append(
                f"   {e['source']} ↔ {e['target']} "
                f"({e.get('connection_count', 0)} connections)"
            )
    return "\n".join(lines)


# ── High-Level API (used by MCP tools) ────────────────────────────────────────


def do_search(query: str, top_k: int = 5) -> dict:
    """Search across all local knowledge bases.

    Auto-detects retrieval tier:
      Tier 1: knowhere-kb (semantic retrieval, if installed)
      Tier 2: Built-in keyword + KG search (fallback)

    Returns search results and records chunk hits for importance tracking.
    """
    # ── Tier 1: Try knowhere-kb semantic retrieval ─────────────────────────
    try:
        from knowhere_kb import search as kb_search
        results = kb_search(query, top_k=top_k, knowhere_home=KNOWHERE_HOME)
        return {
            "status": "ok",
            "tier": 1,
            "engine": "knowhere-kb",
            "query": query,
            "results_count": len(results),
            "results": results,
        }
    except ImportError:
        pass  # knowhere-kb not installed, fall through to Tier 2

    # ── Tier 2: Built-in keyword + KG search ──────────────────────────────
    kbs = discover_knowledge_bases()
    if not kbs:
        return {
            "status": "no_knowledge_base",
            "message": (
                f"未找到知识库。请确保已通过 Knowhere 解析文档。"
                f"数据目录: {KNOWHERE_HOME}"
            ),
        }

    all_results = []
    for kb_id, kg_path in kbs.items():
        graph = load_graph(kg_path)
        kb_dir = os.path.dirname(kg_path)
        chunks = load_chunks_for_kb(kb_dir)
        results = search_chunks(query, chunks, graph, top_k)
        for r in results:
            r["kb_id"] = kb_id
        all_results.extend(results)

    # Sort across all KBs, keep top_k
    all_results.sort(key=lambda x: x["score"], reverse=True)
    all_results = all_results[:top_k]

    # Record chunk hits for importance tracking (non-critical)
    try:
        hits_by_kb: Dict[str, list] = {}
        for r in all_results:
            hits_by_kb.setdefault(r["kb_id"], []).append(r["chunk_id"])
        for kid, cids in hits_by_kb.items():
            record_chunk_hits(kid, cids)
    except Exception:
        pass

    return {
        "status": "ok",
        "tier": 2,
        "engine": "keyword+kg",
        "query": query,
        "results_count": len(all_results),
        "results": all_results,
    }


def do_overview() -> dict:
    """Get structural overview of all local knowledge bases."""
    kbs = discover_knowledge_bases()
    if not kbs:
        return {
            "status": "no_knowledge_base",
            "message": (
                f"未找到知识库。请确保已通过 Knowhere 解析文档。"
                f"数据目录: {KNOWHERE_HOME}"
            ),
        }

    overview = {"status": "ok", "knowledge_bases": []}
    for kb_id, kg_path in kbs.items():
        graph = load_graph(kg_path)
        if not graph:
            continue
        files = graph.get("files", {})
        edges = graph.get("edges", [])
        overview_text = format_files_overview(files, edges)
        overview["knowledge_bases"].append({
            "kb_id": kb_id,
            "version": graph.get("version", "1.0"),
            "stats": graph.get("stats", {}),
            "updated_at": graph.get("updated_at", ""),
            "files_overview": overview_text,
        })

    return overview
