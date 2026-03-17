"""
ConnectTo Builder — KB-level post-processor for inter-chunk relationships.

This module discovers relationships between chunks across different files
within a knowledge base, populating the `connectto` column in the DataFrame.

Phase 1 (this file):  Keyword-overlap "related" relationship.
Phase 2 (TODO):       Embedding cosine similarity (additive scoring).
Phase 3 (TODO):       LLM-based relation classification (contradicts, causal, etc.).
"""

import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ─── Relation Type Registry (extensible, not hard-coded) ──────────────────────

RELATION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "related": {
        "description": "Chunks share common concepts or topics",
        "requires_llm": False,
    },
    # TODO: LLM-classified relation types — uncomment when classify_relation() is implemented
    # "contradicts": {
    #     "description": "Chunks describe opposing or contradictory facts",
    #     "requires_llm": True,
    # },
    # "causal": {
    #     "description": "Chunks have a cause-effect relationship",
    #     "requires_llm": True,
    # },
    # "extends": {
    #     "description": "One chunk extends or improves upon the other",
    #     "requires_llm": True,
    # },
    # "supports": {
    #     "description": "One chunk provides evidence supporting the other",
    #     "requires_llm": True,
    # },
    # "same_method": {
    #     "description": "Chunks discuss the same methodology or technique",
    #     "requires_llm": True,
    # },
    # "same_data": {
    #     "description": "Chunks reference the same dataset",
    #     "requires_llm": True,
    # },
}


# ─── Default Configuration ────────────────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    # Minimum number of shared keywords to consider a connection
    "min_keyword_overlap": 2,
    # Weight multiplier for keyword score (linear)
    "keyword_score_weight": 1.0,
    # Maximum connections per chunk (top-N by score)
    "max_connections_per_chunk": 10,
    # Minimum score threshold to create a connection
    "min_score_threshold": 0.3,
    # Only connect chunks from different files (skip intra-file)
    "cross_file_only": True,
}


# ─── Keyword Normalization ────────────────────────────────────────────────────

# TODO: Synonym dictionary for advanced normalization (e.g. "RL" ↔ "reinforcement learning")
_SYNONYM_MAP: Dict[str, str] = {}


def _normalize_keyword(keyword: str) -> str:
    """
    Normalize a keyword for matching:
      - lowercase
      - strip whitespace
      - collapse multiple spaces
      - apply synonym mapping (TODO)

    Args:
        keyword: Raw keyword string.

    Returns:
        Normalized keyword string.
    """
    kw = keyword.lower().strip()
    kw = re.sub(r"\s+", " ", kw)

    # Apply synonym mapping if available
    return _SYNONYM_MAP.get(kw, kw)


def _extract_file_key(path: str) -> str:
    """
    Extract a file-level key from a chunk's path to determine
    whether two chunks belong to the same file.

    Example paths:
        "Default_Root/paper.pdf/Section 1/Subsection" → "Default_Root/paper.pdf"
        "KB_DATA/reports/annual.docx/Table 1"          → "KB_DATA/reports/annual.docx"

    Heuristic: take the path up to and including the first segment
    that looks like a filename (has an extension).
    """
    if not path:
        return ""

    parts = path.replace("\\", "/").split("/")
    file_parts = []
    for part in parts:
        file_parts.append(part)
        # Check if this segment looks like a file (has extension)
        if "." in part and not part.startswith("."):
            break

    return "/".join(file_parts)


# ─── Keyword Inverted Index ──────────────────────────────────────────────────

def _build_keyword_index(
    chunks: List[Dict[str, Any]],
) -> Dict[str, List[Tuple[str, str]]]:
    """
    Build an inverted index: normalized_keyword → [(chunk_id, file_key)].

    Args:
        chunks: List of chunk dicts, each having:
            - "chunk_id": str
            - "metadata" or "keywords": keyword source
            - "path": str

    Returns:
        Dict mapping normalized keyword → list of (chunk_id, file_key) tuples.
    """
    index: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id") or chunk.get("know_id", "")
        path = chunk.get("path", "")
        file_key = _extract_file_key(path)

        # Extract keywords from metadata or top-level
        keywords = _get_keywords(chunk)
        if not keywords:
            continue

        for kw in keywords:
            normalized = _normalize_keyword(kw)
            if normalized:
                index[normalized].append((str(chunk_id), file_key))

    return dict(index)


def _get_keywords(chunk: Dict[str, Any]) -> List[str]:
    """
    Extract keywords from a chunk, supporting multiple input formats:
      - chunk["metadata"]["keywords"] (list)
      - chunk["keywords"] (list or semicolon-separated string)
      - chunk["metadata"]["tokens"] or chunk["tokens"] (fallback: jieba word chain)
    """
    # Try metadata.keywords first
    metadata = chunk.get("metadata", {})
    if isinstance(metadata, dict):
        kws = metadata.get("keywords", [])
        if isinstance(kws, list) and kws:
            return kws

    # Try top-level keywords
    kws = chunk.get("keywords", [])
    if isinstance(kws, list) and kws:
        return kws
    if isinstance(kws, str) and kws.strip():
        # Parse semicolon or comma separated
        if ";" in kws:
            return [k.strip() for k in kws.split(";") if k.strip()]
        elif "," in kws:
            return [k.strip() for k in kws.split(",") if k.strip()]
        return [kws.strip()]

    # ─── Fallback: tokens (jieba word chain) ──────────────────────────────
    tokens = _parse_tokens_field(metadata.get("tokens") if isinstance(metadata, dict) else None)
    if not tokens:
        tokens = _parse_tokens_field(chunk.get("tokens"))
    return tokens


# Pre-compiled patterns for token noise filtering
_UUID_LIKE_RE = re.compile(r"^[0-9a-f]{4,}$", re.IGNORECASE)
_MARKER_PREFIXES = ("IMAGE_", "TABLE_", "PTXT", "image-", "table-")


def _parse_tokens_field(raw) -> List[str]:
    """
    Parse the tokens field into a filtered keyword list.

    Accepts:
      - List[str]: already parsed (from chunks.json after safe_parse_tokens)
      - str with ';': semicolon-separated tokens (new format, matches keywords)
      - str with '->': arrow-separated jieba word chain (legacy format)
      - str with "['...']": legacy list-repr format

    Filters out noise: single-char tokens, UUIDs, IMAGE_/TABLE_ markers.
    """
    if raw is None:
        return []

    # Already a list (from chunks.json)
    if isinstance(raw, list):
        words = raw
    elif isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        # List-repr format: "['w1;w2;w3']" or "['w1->w2->w3']"
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if (inner.startswith("'") and inner.endswith("'")) or \
               (inner.startswith('"') and inner.endswith('"')):
                inner = inner[1:-1]
            raw = inner
        # Determine separator: semicolon (new) or arrow (legacy)
        if ";" in raw:
            words = [t.strip() for t in raw.split(";") if t.strip()]
        elif "->" in raw:
            words = [t.strip() for t in raw.split("->") if t.strip()]
        else:
            return []
    else:
        return []

    # Filter noise
    filtered = []
    for w in words:
        if len(w) <= 1:
            continue
        if any(w.startswith(p) for p in _MARKER_PREFIXES):
            continue
        if _UUID_LIKE_RE.match(w):
            continue
        filtered.append(w)
    return filtered


# ─── Scoring ─────────────────────────────────────────────────────────────────

def _compute_keyword_score(
    shared_count: int,
    total_a: int,
    total_b: int,
    weight: float = 1.0,
) -> float:
    """
    Compute keyword overlap score using linear proportional scoring.

    Formula: score = weight * shared_count / min(total_a, total_b)

    This is linear — more shared keywords = higher score, as requested.

    Args:
        shared_count: Number of overlapping keywords.
        total_a: Total keywords in chunk A.
        total_b: Total keywords in chunk B.
        weight: Score multiplier.

    Returns:
        Float score in [0, weight].
    """
    denominator = min(total_a, total_b)
    if denominator == 0:
        return 0.0
    return weight * shared_count / denominator


# ─── Main Entry Point ────────────────────────────────────────────────────────

def build_connections(
    chunks: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Compute "related" connections between chunks based on keyword overlap.

    Args:
        chunks: List of chunk dicts. Each must have:
            - chunk_id (or know_id): str
            - path: str
            - metadata.keywords or keywords: List[str]
        config: Optional overrides for DEFAULT_CONFIG.

    Returns:
        Dict mapping chunk_id → list of connection dicts:
        [{"target": "...", "relation": "related", "score": 0.82, "keywords": ["PPO", "RL"]}]
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    min_overlap = cfg["min_keyword_overlap"]
    kw_weight = cfg["keyword_score_weight"]
    max_conns = cfg["max_connections_per_chunk"]
    min_score = cfg["min_score_threshold"]
    cross_only = cfg["cross_file_only"]

    # Build inverted index
    kw_index = _build_keyword_index(chunks)

    # Pre-compute per-chunk data
    chunk_data: Dict[str, Tuple[str, set]] = {}  # chunk_id → (file_key, normalized_keywords)
    for chunk in chunks:
        cid = str(chunk.get("chunk_id") or chunk.get("know_id", ""))
        if not cid:
            continue
        file_key = _extract_file_key(chunk.get("path", ""))
        kws = _get_keywords(chunk)
        normalized_kws = {_normalize_keyword(k) for k in kws if k}
        normalized_kws.discard("")
        chunk_data[cid] = (file_key, normalized_kws)

    # For each chunk, find candidates via keyword index
    connections: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for cid, (file_key, my_kws) in chunk_data.items():
        if not my_kws:
            continue

        # Collect candidates and their shared keywords
        candidate_shared: Dict[str, set] = defaultdict(set)  # target_id → shared_kw set

        for kw in my_kws:
            entries = kw_index.get(kw, [])
            for target_id, target_file in entries:
                if target_id == cid:
                    continue
                if cross_only and target_file == file_key:
                    continue
                candidate_shared[target_id].add(kw)

        # Score and filter candidates
        scored: List[Tuple[str, float, set]] = []
        for target_id, shared_kws in candidate_shared.items():
            if len(shared_kws) < min_overlap:
                continue

            target_data = chunk_data.get(target_id)
            if not target_data:
                continue

            _, target_kws = target_data
            score = _compute_keyword_score(
                shared_count=len(shared_kws),
                total_a=len(my_kws),
                total_b=len(target_kws),
                weight=kw_weight,
            )
            if score >= min_score:
                scored.append((target_id, score, shared_kws))

        # Sort by score descending, keep top-N
        scored.sort(key=lambda x: x[1], reverse=True)
        for target_id, score, shared_kws in scored[:max_conns]:
            connections[cid].append({
                "target": target_id,
                "relation": "related",
                "score": round(score, 4),
                "keywords": sorted(shared_kws),
            })

    total_edges = sum(len(v) for v in connections.values())
    logger.info(
        f"🔗 ConnectTo: {total_edges} connections found "
        f"across {len(connections)} chunks "
        f"(config: min_overlap={min_overlap}, threshold={min_score})"
    )

    return dict(connections)


# ─── Serialization ────────────────────────────────────────────────────────────

def serialize_connections(connections: List[Dict[str, Any]]) -> str:
    """
    Serialize a chunk's connection list to a JSON string
    for storage in the `connectto` DataFrame column.

    Args:
        connections: List of connection dicts.

    Returns:
        JSON string, or empty string if no connections.
    """
    if not connections:
        return ""
    return json.dumps(connections, ensure_ascii=False, separators=(",", ":"))


def deserialize_connections(raw: Any) -> List[Dict[str, Any]]:
    """
    Deserialize the `connectto` column value back to a list of connections.

    Handles:
      - JSON array string: '[{"target": "...", ...}]'
      - Empty / NaN / None: returns []
      - Legacy newline-separated format: returns as-is strings (backward compat)

    Args:
        raw: Raw value from DataFrame connectto column.

    Returns:
        List of connection dicts.
    """
    if raw is None:
        return []

    try:
        import pandas as pd
        if pd.isna(raw):
            return []
    except (ImportError, TypeError, ValueError):
        pass

    raw_str = str(raw).strip()
    if not raw_str:
        return []

    # Try JSON parse first
    if raw_str.startswith("["):
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    # Legacy format: newline-separated strings → wrap in basic structure
    if "\n" in raw_str:
        lines = [line.strip() for line in raw_str.split("\n") if line.strip()]
        return [{"target": line, "relation": "related", "score": 1.0, "keywords": []} for line in lines]

    # Single value
    if raw_str:
        return [{"target": raw_str, "relation": "related", "score": 1.0, "keywords": []}]

    return []


# ─── LLM Relation Classification (stub) ──────────────────────────────────────

def classify_relation(
    summary_a: str,
    summary_b: str,
    shared_keywords: List[str],
    llm_client: Any = None,
) -> Dict[str, Any]:
    """
    Classify the specific relation type between two related chunks using LLM.

    This function is a **stub** — the concrete classification prompt and LLM
    call logic are TODO. Currently returns "related" for all pairs.

    Args:
        summary_a: Summary text of chunk A.
        summary_b: Summary text of chunk B.
        shared_keywords: Keywords they share.
        llm_client: Optional LLM client for making classification calls.

    Returns:
        Dict with keys:
            - "relation": str (from RELATION_REGISTRY)
            - "reason": str (human-readable explanation)
            - "confidence": float (0.0 ~ 1.0)

    TODO: Implement classification prompt:
        Given two knowledge chunks:
        [Chunk A]: {summary_a}
        [Chunk B]: {summary_b}
        Shared concepts: {shared_keywords}

        Classify their relationship:
        - contradicts: A and B describe opposing facts
        - causal: A and B have a cause-effect relationship
        - extends: B extends or improves upon A
        - supports: B provides evidence for A
        - same_method: A and B use the same methodology
        - same_data: A and B use the same dataset
        - related: Related but none of the above
        - other: Has a clear relationship not listed above (describe it)

        Return JSON: {"relation": "...", "reason": "...", "confidence": 0.0~1.0}
    """
    return {
        "relation": "related",
        "reason": f"Keyword overlap: {', '.join(shared_keywords)}" if shared_keywords else "Keyword overlap",
        "confidence": 1.0,
    }
