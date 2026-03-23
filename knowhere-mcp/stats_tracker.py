"""
Chunk usage statistics tracker for Knowhere knowledge bases.

Tracks how often chunks are accessed (hit) during search operations.
These stats feed into file importance calculation during knowledge graph rebuilds.

Data is stored as ~/.knowhere/{kb_id}/chunk_stats.json

This module has ZERO dependencies on connect_builder or any worker code.
It only does file I/O on JSON files.
"""

import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── Configuration ─────────────────────────────────────────────────────────────

KNOWHERE_HOME = os.path.expanduser(
    os.environ.get("KNOWHERE_HOME", "~/.knowhere")
)


def _get_stats_path(kb_id: str) -> str:
    """Get the chunk_stats.json path for a KB."""
    return os.path.join(KNOWHERE_HOME, kb_id, "chunk_stats.json")


# ── Core Functions ────────────────────────────────────────────────────────────


def load_chunk_stats(kb_id: str) -> Dict[str, Dict[str, Any]]:
    """Load chunk usage stats from chunk_stats.json.

    Returns:
        Dict mapping chunk_id → {hit_count, first_hit, last_hit, created_at}
    """
    path = _get_stats_path(kb_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def record_chunk_hits(
    kb_id: str,
    chunk_ids: List[str],
) -> None:
    """Record that chunks were accessed (returned in search results).

    Updates hit_count and last_hit for each chunk.
    Creates chunk_stats.json if it doesn't exist.

    Args:
        kb_id: Knowledge base ID.
        chunk_ids: List of chunk IDs that were hit.
    """
    if not chunk_ids:
        return

    stats = load_chunk_stats(kb_id)
    now = datetime.now(timezone.utc).isoformat()

    for cid in chunk_ids:
        if cid not in stats:
            stats[cid] = {
                "hit_count": 0,
                "first_hit": now,
                "last_hit": now,
                "created_at": now,
            }
        stats[cid]["hit_count"] += 1
        stats[cid]["last_hit"] = now

    path = _get_stats_path(kb_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def relevance_score(
    hit_count: int,
    last_hit_iso: Optional[str],
    half_life_days: float = 30.0,
) -> float:
    """Compute relevance score with exponential decay.

    Higher hit_count + more recent access → higher score.

    Args:
        hit_count: Number of times this chunk was accessed.
        last_hit_iso: ISO timestamp of last access.
        half_life_days: Days until relevance halves.

    Returns:
        Decay-weighted score.
    """
    if not last_hit_iso:
        return 0.0
    try:
        last_hit_dt = datetime.fromisoformat(last_hit_iso)
        days_since = (datetime.now(timezone.utc) - last_hit_dt).total_seconds() / 86400
    except (ValueError, TypeError):
        days_since = 0

    decay = math.exp(-0.693 * days_since / half_life_days)
    return hit_count * decay
