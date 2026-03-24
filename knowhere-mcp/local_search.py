"""
Local knowledge base search for Knowhere MCP Server.

Reads from KNOWHERE_HOME (default: ~/.knowhere/) to provide:
  - Tier 2: LLM-as-Retriever tools (get_knowledge_map, get_document_structure,
            read_document_chunks, discover_relevant_files)
  - Tier 3: Code-level keyword + KG search (search_knowledge fallback)

File-level usage stats (hit_count, last_hit) are stored directly in
knowledge_graph.json → files.{doc_name}, eliminating the need for a
separate chunk_stats.json.

Zero dependencies on worker code or connect_builder.
"""

import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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


def _load_json(path: str) -> Optional[Any]:
    """Load a JSON file, returning None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _save_json(path: str, data: Any) -> None:
    """Save data to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _find_doc_dir(kb_dir: str, doc_name: str) -> Optional[str]:
    """Find the document subdirectory by name (exact or fuzzy match)."""
    exact = os.path.join(kb_dir, doc_name)
    if os.path.isdir(exact):
        return exact
    for entry in os.listdir(kb_dir):
        entry_path = os.path.join(kb_dir, entry)
        if os.path.isdir(entry_path) and doc_name in entry:
            return entry_path
    return None


def _load_chunks_for_doc(doc_dir: str) -> List[Dict[str, Any]]:
    """Load chunks from a document directory, preferring slim version."""
    slim = os.path.join(doc_dir, "chunks_slim.json")
    full = os.path.join(doc_dir, "chunks.json")

    chosen = slim if os.path.isfile(slim) else full if os.path.isfile(full) else None
    if not chosen:
        return []

    data = _load_json(chosen)
    if not data:
        return []

    chunks = data.get("chunks", data) if isinstance(data, dict) else data
    is_slim = (chosen == slim)

    # If reading full chunks.json, strip to slim fields in memory
    if not is_slim and isinstance(chunks, list):
        stripped = []
        for c in chunks:
            meta = c.get("metadata", {}) if isinstance(c.get("metadata"), dict) else {}
            stripped.append({
                "type": c.get("type", "text"),
                "path": c.get("path", ""),
                "content": c.get("content", ""),
                "summary": meta.get("summary") or c.get("summary", ""),
            })
        return stripped

    return chunks if isinstance(chunks, list) else []


# ── File-Level Usage Tracking (in knowledge_graph.json) ──────────────────────


def _record_file_hit(kb_id: str, doc_name: str) -> None:
    """Record a file access hit in knowledge_graph.json.

    Updates hit_count, last_hit, and recalculates importance for the file.
    """
    kg_path = os.path.join(KNOWHERE_HOME, kb_id, "knowledge_graph.json")
    graph = _load_json(kg_path)
    if not graph:
        return

    files = graph.get("files", {})
    if doc_name not in files:
        return

    now = datetime.now(timezone.utc).isoformat()
    finfo = files[doc_name]
    finfo["hit_count"] = finfo.get("hit_count", 0) + 1
    finfo["last_hit"] = now

    # Recalculate importance: α × usage_heat + β × freshness
    hit_count = finfo["hit_count"]
    last_hit = finfo["last_hit"]
    created_at = finfo.get("created_at", now)

    half_life = 30.0
    alpha, beta = 0.7, 0.3

    usage_heat = _decay_score(hit_count, last_hit, half_life)
    freshness = _decay_score(1, created_at, half_life)
    finfo["importance"] = round(alpha * usage_heat + beta * freshness, 4)

    graph["updated_at"] = now
    _save_json(kg_path, graph)


def _decay_score(hit_count: int, iso_time: str, half_life_days: float) -> float:
    """Exponential decay score: higher hits + more recent → higher score."""
    try:
        dt = datetime.fromisoformat(iso_time)
        days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except (ValueError, TypeError):
        days = 0
    return hit_count * math.exp(-0.693 * days / half_life_days)


# ══════════════════════════════════════════════════════════════════════════════
#  TIER 2: LLM-as-Retriever Tools
# ══════════════════════════════════════════════════════════════════════════════


def do_get_knowledge_map(kb_id: Optional[str] = None) -> dict:
    """Return knowledge graph metadata for one or all KBs.

    This is the LLM's "bird's-eye view" — file names, keywords, importance,
    chunk counts, and cross-file connections. LLM uses this to decide which
    documents are relevant to the user's query.
    """
    kbs = discover_knowledge_bases()
    if not kbs:
        return {
            "status": "no_knowledge_base",
            "message": f"未找到知识库。数据目录: {KNOWHERE_HOME}",
        }

    if kb_id:
        if kb_id not in kbs:
            return {"status": "not_found", "message": f"知识库 '{kb_id}' 不存在"}
        kbs = {kb_id: kbs[kb_id]}

    result = {"status": "ok", "knowledge_bases": []}
    for kid, kg_path in kbs.items():
        graph = _load_json(kg_path)
        if not graph:
            continue
        result["knowledge_bases"].append({
            "kb_id": kid,
            "version": graph.get("version", "1.0"),
            "updated_at": graph.get("updated_at", ""),
            "stats": graph.get("stats", {}),
            "files": graph.get("files", {}),
            "edges": graph.get("edges", []),
        })

    return result


def do_get_document_structure(kb_id: str, doc_name: str) -> dict:
    """Return the hierarchy (TOC) of a specific document.

    LLM uses this to understand the document's chapter/section structure
    and decide which sections to read.
    """
    kb_dir = os.path.join(KNOWHERE_HOME, kb_id)
    if not os.path.isdir(kb_dir):
        return {"status": "not_found", "message": f"知识库 '{kb_id}' 不存在"}

    doc_dir = _find_doc_dir(kb_dir, doc_name)
    if not doc_dir:
        return {"status": "not_found", "message": f"文档 '{doc_name}' 不存在"}

    hierarchy_path = os.path.join(doc_dir, "hierarchy.json")
    hierarchy = _load_json(hierarchy_path)

    if hierarchy:
        return {
            "status": "ok",
            "kb_id": kb_id,
            "doc_name": os.path.basename(doc_dir),
            "hierarchy": hierarchy,
        }

    # Fallback: build a simple structure from chunk paths
    chunks = _load_chunks_for_doc(doc_dir)
    paths = sorted(set(c.get("path", "") for c in chunks if c.get("path")))
    return {
        "status": "ok",
        "kb_id": kb_id,
        "doc_name": os.path.basename(doc_dir),
        "hierarchy": None,
        "chunk_paths": paths,
        "message": "无 hierarchy.json，已返回所有 chunk 路径供参考",
    }


def do_read_chunks(
    kb_id: str,
    doc_name: str,
    section_path: Optional[str] = None,
    max_chunks: int = 50,
) -> dict:
    """Read chunks from a specific document, optionally filtered by section path.

    If section_path is provided, only chunks whose path contains that string
    are returned. This allows the LLM to read specific chapters/sections
    without loading the entire document.
    """
    kb_dir = os.path.join(KNOWHERE_HOME, kb_id)
    if not os.path.isdir(kb_dir):
        return {"status": "not_found", "message": f"知识库 '{kb_id}' 不存在"}

    doc_dir = _find_doc_dir(kb_dir, doc_name)
    if not doc_dir:
        return {"status": "not_found", "message": f"文档 '{doc_name}' 不存在"}

    chunks = _load_chunks_for_doc(doc_dir)

    # Filter by section path if specified
    if section_path:
        chunks = [c for c in chunks if section_path in c.get("path", "")]

    total = len(chunks)
    truncated = total > max_chunks
    chunks = chunks[:max_chunks]

    # Record file-level access in knowledge_graph.json
    try:
        _record_file_hit(kb_id, os.path.basename(doc_dir))
    except Exception:
        pass

    return {
        "status": "ok",
        "kb_id": kb_id,
        "doc_name": os.path.basename(doc_dir),
        "section_path": section_path,
        "total_chunks": total,
        "returned_chunks": len(chunks),
        "truncated": truncated,
        "chunks": chunks,
    }


def do_discover_files(query: str, kb_id: Optional[str] = None) -> dict:
    """Bottom-up discovery: grep all chunks for query terms, return file hit stats.

    This complements the top-down approach (get_knowledge_map) by finding files
    that contain the query terms in their actual content, even if the file-level
    keywords don't match.

    Returns file names + hit counts, NOT chunk content (lightweight).
    LLM should union this with its top-down selection from get_knowledge_map.
    """
    query_terms = _tokenize_query(query)
    if not query_terms:
        return {"status": "no_query", "message": "查询为空"}

    kbs = discover_knowledge_bases()
    if kb_id:
        kbs = {k: v for k, v in kbs.items() if k == kb_id}
    if not kbs:
        return {"status": "no_knowledge_base"}

    file_hits: Dict[str, Dict[str, int]] = {}

    for kid, kg_path in kbs.items():
        kb_dir = os.path.dirname(kg_path)
        for entry in os.listdir(kb_dir):
            entry_path = os.path.join(kb_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            chunks = _load_chunks_for_doc(entry_path)
            hits = 0
            for chunk in chunks:
                content = chunk.get("content", "") + " " + chunk.get("summary", "")
                hits += sum(1 for t in query_terms if t in content)
            if hits > 0:
                if kid not in file_hits:
                    file_hits[kid] = {}
                file_hits[kid][entry] = hits

    results = []
    for kid, files in file_hits.items():
        for fname, hits in sorted(files.items(), key=lambda x: x[1], reverse=True):
            results.append({
                "kb_id": kid,
                "doc_name": fname,
                "hit_count": hits,
            })

    results.sort(key=lambda x: x["hit_count"], reverse=True)

    return {
        "status": "ok",
        "query": query,
        "query_terms": list(query_terms),
        "discovered_files": results,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  TIER 3: Code-Level Keyword + KG Search (Fallback)
# ══════════════════════════════════════════════════════════════════════════════


def _tokenize_query(query: str) -> set:
    """Simple tokenization for search queries."""
    try:
        import jieba
        return set(w for w in jieba.cut(query) if len(w) > 1)
    except ImportError:
        tokens = re.split(r'[\s,;，；。！？、\-/]+', query)
        return set(t for t in tokens if len(t) > 1)


def _load_all_chunks_for_kb(kb_dir: str) -> List[Dict[str, Any]]:
    """Load all chunks from a KB for Tier 3 search."""
    all_chunks = []
    for entry in os.listdir(kb_dir):
        entry_path = os.path.join(kb_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        chunks = _load_chunks_for_doc(entry_path)
        for c in chunks:
            c["_source_file"] = entry
        all_chunks.extend(chunks)
    return all_chunks


def search_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    graph: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Keyword search over chunks with KG edge context."""
    query_terms = _tokenize_query(query)
    if not query_terms:
        return []

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
        summary = chunk.get("summary", "")
        keywords = set(chunk.get("keywords", []))

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
            "type": chunk.get("type", "text"),
            "path": chunk.get("path", ""),
            "score": round(score, 2),
            "content_preview": content[:800],
            "summary": chunk.get("summary", ""),
            "source_file": chunk.get("_source_file", ""),
        }

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


def do_search(query: str, top_k: int = 5) -> dict:
    """Tier 3: Search across all local knowledge bases using keyword matching."""
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
        pass

    # ── Tier 3: Built-in keyword + KG search ──────────────────────────────
    kbs = discover_knowledge_bases()
    if not kbs:
        return {
            "status": "no_knowledge_base",
            "message": f"未找到知识库。数据目录: {KNOWHERE_HOME}",
        }

    all_results = []
    for kb_id, kg_path in kbs.items():
        graph = _load_json(kg_path)
        kb_dir = os.path.dirname(kg_path)
        chunks = _load_all_chunks_for_kb(kb_dir)
        results = search_chunks(query, chunks, graph, top_k)
        for r in results:
            r["kb_id"] = kb_id
        all_results.extend(results)

    all_results.sort(key=lambda x: x["score"], reverse=True)
    all_results = all_results[:top_k]

    # Record file-level hits in knowledge_graph.json
    try:
        hit_files: Dict[str, set] = {}
        for r in all_results:
            kid = r.get("kb_id", "")
            sf = r.get("source_file", "")
            if kid and sf:
                hit_files.setdefault(kid, set()).add(sf)
        for kid, doc_names in hit_files.items():
            for dn in doc_names:
                _record_file_hit(kid, dn)
    except Exception:
        pass

    return {
        "status": "ok",
        "tier": 3,
        "engine": "keyword+kg",
        "query": query,
        "results_count": len(all_results),
        "results": all_results,
    }
