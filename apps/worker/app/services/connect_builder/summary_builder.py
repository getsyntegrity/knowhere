"""
summary_builder: Bottom-up recursive summarization for document hierarchies.

Reads hierarchy.json + chunks.json for a file, builds a tree, and generates
`_summary` fields at every intermediate node via LLM aggregation.
The enriched hierarchy.json is written back to disk.

Usage (standalone):
    from app.services.connect_builder.summary_builder import enrich_hierarchy_summaries
    enrich_hierarchy_summaries(kb_dir, source_file="report.pdf")

Called by graph_builder.build_and_deploy() after file deploy, before KG build.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from shared.utils.chunk_refs import CHUNK_REF_PATTERN, REFERENCE_LABEL_PATTERN


# ─── Constants ────────────────────────────────────────────────────────────────

# Summary output max length (≤100 chars)
SUMMARY_MAX_LEN = 100

# Maximum snippet length per chunk used as input material
CHUNK_SNIPPET_MAX = 200

# Summary marker key in hierarchy.json
SUMMARY_KEY = "_summary"

# Keys in hierarchy.json that are not content tree nodes
RESERVED_KEYS = {"images", "tables", SUMMARY_KEY}


# ─── LLM Interface ───────────────────────────────────────────────────────────


def _llm_summarize(snippets_text: str, node_name: str) -> str:
    """
    Call LLM to produce a concise summary from aggregated child snippets.

    Returns plain text summary (≤100 chars), or "" on failure.
    """
    try:
        from shared.services.ai.prompt_service import build_prompt, _detect_text_language
        from shared.utils.OpenAICompatibleClientSync import get_openai_client

        # Deterministic language lock — see prompt_service._language_directive
        detected_lang = _detect_text_language(snippets_text)
        prompt, temperature, top_p, max_tokens = build_prompt(
            task="file-summary",
            texts=snippets_text,
            query="",
            paras={
                "max_tokens": 100,
                "node_name": node_name,
                "lang": detected_lang,
            },
        )
        messages = [
            {"role": "system", "content": "you are a helpful assistant"},
            {"role": "user", "content": prompt},
        ]
        resp = get_openai_client().chat_completion(
            messages=messages,
            timeout=60,
            max_tokens=max_tokens,
        )
        if resp is None:
            return ""
        if isinstance(resp, str):
            stripped = resp.strip()
            if stripped.lower() in ("null", "none"):
                return ""
            return stripped
        return ""
    except Exception as e:
        logger.warning(f"LLM summary failed for '{node_name}': {e}")
        return ""


# ─── Chunk Lookup ─────────────────────────────────────────────────────────────


def _build_chunk_lookup(
    chunks: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Build a mapping from the LAST path segment to a snippet string.

    For each chunk, compose a structured snippet:
      - If metadata.summary exists → use it directly
      - Otherwise → title (node_key) + keywords + content[:200]
    """
    marker_re = re.compile(CHUNK_REF_PATTERN, re.IGNORECASE)
    # Also strip standalone table/image reference lines like "table-4", "image-1"
    ref_re = re.compile(REFERENCE_LABEL_PATTERN, re.IGNORECASE)
    lookup: Dict[str, str] = {}

    for chunk in chunks:
        path = chunk.get("path", "")
        if not path:
            continue

        ctype = chunk.get("type", "text")
        # Skip image and table chunks — they have their own summaries
        # but don't belong to the content tree path hierarchy
        if ctype in ("image", "table"):
            continue

        # Use the last path segment as tree node key
        parts = path.rstrip("/").split("/")
        node_key = parts[-1] if parts else ""
        if not node_key:
            continue

        meta = chunk.get("metadata", {})
        summary = ""
        if isinstance(meta, dict):
            summary = (meta.get("summary") or "").strip()

        if not summary:
            # Compose from: title + keywords + content[:200]
            snippet_parts = []

            # Content excerpt (stripped of IMAGE/TABLE markers and ref lines)
            content = chunk.get("content", "")
            lines = content.split("\n")
            clean_lines = [
                l for l in lines
                if not marker_re.search(l) and not ref_re.match(l)
            ]
            clean_text = "\n".join(clean_lines).strip()

            if not clean_text and not (isinstance(meta, dict) and meta.get("keywords")):
                # Avoid generating a trivial title-only snippet if there's no actual content
                summary = ""
            else:
                snippet_parts = []
                snippet_parts.append(node_key)
                
                if isinstance(meta, dict):
                    kw = (meta.get("keywords") or "").strip()
                    if kw:
                        snippet_parts.append(f"Keywords: {kw}")

                if clean_text:
                    snippet_parts.append(clean_text[:CHUNK_SNIPPET_MAX])

                summary = "\n".join(snippet_parts)

        if summary:
            # Multiple chunks may share the same last segment (e.g. "part 1", "part 2")
            if node_key in lookup:
                lookup[node_key] = lookup[node_key] + "\n" + summary
            else:
                lookup[node_key] = summary

    return lookup


# ─── Recursive Summarization ─────────────────────────────────────────────────


def _recursive_summarize(
    tree: Dict[str, Any],
    chunk_lookup: Dict[str, str],
    path_prefix: str = "",
    use_llm: bool = True,
) -> str:
    """
    Bottom-up recursive summarization on a hierarchy tree node.

    For each node in the tree:
    - If it's a leaf (empty dict) → return chunk snippet from lookup
    - If it has children → recursively summarize children first,
      then aggregate their summaries into this node's summary

    When use_llm=False, always uses title enumeration instead of calling
    the LLM. This produces a lightweight summary like:
      "This section covers: Section 1, Section 2, Section 3"

    Writes the summary into the tree dict in-place as `_summary`.

    Returns the generated summary string for this node.
    """
    # Collect child keys (skip reserved keys)
    child_keys = [k for k in tree.keys() if k not in RESERVED_KEYS]

    if not child_keys:
        # Leaf node — return snippet from chunk lookup
        # Use last segment of path_prefix as lookup key
        node_name = path_prefix.split("/")[-1] if path_prefix else ""
        snippet = chunk_lookup.get(node_name, "")
        if snippet:
            # Note: Leaf snippets rely on _build_chunk_lookup to provide the proper 
            # length. If it's from metadata.summary, it is used directly without truncation.
            tree[SUMMARY_KEY] = snippet
        else:
            # Clean up any stale _summary from previous runs
            tree.pop(SUMMARY_KEY, None)
        return snippet

    # Recurse into children, collect their summaries
    child_summaries: List[Tuple[str, str]] = []
    for key in child_keys:
        subtree = tree[key]
        if not isinstance(subtree, dict):
            continue
        child_path = f"{path_prefix}/{key}" if path_prefix else key
        child_summary = _recursive_summarize(subtree, chunk_lookup, child_path, use_llm=use_llm)
        if child_summary:
            child_summaries.append((key, child_summary))

    if not child_summaries:
        return ""

    # Aggregate child summaries
    aggregated_parts = []
    for name, summary in child_summaries:
        # Truncate individual child summaries to keep LLM input manageable
        truncated = summary[:SUMMARY_MAX_LEN]
        aggregated_parts.append(f"[{name}] {truncated}")

    aggregated_text = "\n".join(aggregated_parts)
    node_name = path_prefix.split("/")[-1] if path_prefix else "document"

    # Decide: LLM or direct passthrough / enumeration
    if len(child_summaries) <= 1:
        # Single child — just propagate its summary
        result = child_summaries[0][1][:SUMMARY_MAX_LEN]
    else:
        # Title enumeration (no LLM) — always used when use_llm=False,
        # and also used when total child summary length is short enough
        titles = [name for name, _ in child_summaries]
        title_enum = "This section covers: " + ", ".join(titles)

        if not use_llm:
            # No LLM mode — always use title enumeration
            result = title_enum
        else:
            # LLM mode — only call LLM when content is long enough
            total_len = sum(len(s) for _, s in child_summaries)
            if total_len > SUMMARY_MAX_LEN:
                result = _llm_summarize(aggregated_text, node_name)
                if not result:
                    # LLM failed — fallback to title enumeration
                    result = title_enum
            else:
                result = title_enum

    tree[SUMMARY_KEY] = result
    return result


# ─── Public API ───────────────────────────────────────────────────────────────


def enrich_hierarchy_summaries(
    kb_dir: str,
    source_file: Optional[str] = None,
    force: bool = False,
    use_llm: bool = True,
) -> Dict[str, str]:
    """
    Enrich hierarchy.json with bottom-up recursive summaries for file(s).

    Args:
        kb_dir: Absolute path to the KB directory (e.g. ~/.knowhere/my_kb).
        source_file: If given, only process this file. Otherwise process all.
        force: If True, regenerate summaries even if _summary already exists.
        use_llm: If True, use LLM to generate coherent summaries for long
            content. If False, always use lightweight title enumeration
            (e.g. "This section covers: Section 1, Section 2"). Defaults to True.

    Returns:
        Dict mapping file_name → top-level summary string.
    """
    results: Dict[str, str] = {}
    mode_label = "LLM" if use_llm else "title-concat"

    # Determine which files to process
    if source_file:
        targets = [source_file]
    else:
        targets = [
            entry
            for entry in os.listdir(kb_dir)
            if os.path.isdir(os.path.join(kb_dir, entry))
            and not entry.startswith(".")
        ]

    for file_name in targets:
        file_dir = os.path.join(kb_dir, file_name)
        hierarchy_path = os.path.join(file_dir, "hierarchy.json")
        chunks_path = os.path.join(file_dir, "chunks.json")

        if not os.path.exists(hierarchy_path):
            logger.debug(f"No hierarchy.json for {file_name}, skipping summary")
            continue

        # Check if already has summaries (skip unless forced)
        with open(hierarchy_path, "r", encoding="utf-8") as f:
            hierarchy = json.load(f)

        if not force and _has_summaries(hierarchy):
            logger.debug(f"Summaries already exist for {file_name}, skipping")
            # Extract existing top-level summary
            top_summary = _extract_top_summary(hierarchy, file_name)
            results[file_name] = top_summary
            continue

        # Load chunks for snippet lookup
        chunks = []
        if os.path.exists(chunks_path):
            with open(chunks_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            chunks = data.get("chunks", [])

        # Strip all existing summaries before regenerating (prevent stale residuals)
        if force:
            _strip_summaries(hierarchy)

        chunk_lookup = _build_chunk_lookup(chunks)
        logger.info(
            f"📝 Generating hierarchical summaries for {file_name} "
            f"({len(chunk_lookup)} leaf snippets, mode={mode_label})"
        )

        # Find the content tree root (skip 'images' and 'tables')
        content_keys = [k for k in hierarchy.keys() if k not in RESERVED_KEYS]

        for root_key in content_keys:
            subtree = hierarchy[root_key]
            if isinstance(subtree, dict):
                _recursive_summarize(subtree, chunk_lookup, root_key, use_llm=use_llm)

        # Write enriched hierarchy back
        with open(hierarchy_path, "w", encoding="utf-8") as f:
            json.dump(hierarchy, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Hierarchical summaries saved for {file_name}")

        top_summary = _extract_top_summary(hierarchy, file_name)
        results[file_name] = top_summary

    return results


def _has_summaries(hierarchy: Dict[str, Any]) -> bool:
    """Check if hierarchy already contains _summary fields."""
    for key, val in hierarchy.items():
        if key == SUMMARY_KEY:
            return True
        if isinstance(val, dict) and _has_summaries(val):
            return True
    return False


def _strip_summaries(tree: Dict[str, Any]) -> None:
    """Recursively remove all _summary keys from a hierarchy tree.

    Called before force-regeneration to prevent stale summaries
    from previous runs bleeding into the new pass.
    """
    tree.pop(SUMMARY_KEY, None)
    for key, val in tree.items():
        if isinstance(val, dict) and key not in ("images", "tables"):
            _strip_summaries(val)


def _extract_top_summary(hierarchy: Dict[str, Any], file_name: str) -> str:
    """
    Extract the top-level summary for a file from its enriched hierarchy.

    Looks for the file_name key in the hierarchy tree and returns its _summary.
    Falls back to the first content node's _summary.
    """
    content_keys = [k for k in hierarchy.keys() if k not in RESERVED_KEYS]

    for root_key in content_keys:
        subtree = hierarchy.get(root_key, {})
        if not isinstance(subtree, dict):
            continue

        # Try to find file_name directly under root
        if file_name in subtree:
            file_node = subtree[file_name]
            if isinstance(file_node, dict) and SUMMARY_KEY in file_node:
                return file_node[SUMMARY_KEY]

        # Root itself might have a summary
        if SUMMARY_KEY in subtree:
            return subtree[SUMMARY_KEY]

    # Fallback: return root-level summary if present
    if SUMMARY_KEY in hierarchy:
        return hierarchy[SUMMARY_KEY]

    return ""
