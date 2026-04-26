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
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from openai.types.chat import ChatCompletionMessageParam


# ─── Constants ────────────────────────────────────────────────────────────────

# Summary output max length for recursive LLM aggregation (≤100 chars per node)
SUMMARY_MAX_LEN = 100
# Navigation top-summary budget measured in semantic tokens (count_cn_en)
NAVIGATION_TOP_SUMMARY_MAX_TOKENS = 200
# TODO: revisit this cap after we collect more real-world prompt/token budget data.
NON_LLM_TOP_SUMMARY_MAX_SECTIONS = 20
NON_LLM_TOP_SUMMARY_MAX_DEPTH = 2

# Summary marker key in hierarchy.json
SUMMARY_KEY = "_summary"

# Keys in hierarchy.json that are not content tree nodes
RESERVED_KEYS = {"images", "tables", SUMMARY_KEY}
_TREE_EXCLUDED_TITLES = {"root", "images", "tables"}
_TREE_TITLE_MAX_TOKENS_START = 20
_TREE_TITLE_MAX_TOKENS_END = 5
_TITLE_ENUM_PREFIXES = (
    "this section covers:",
    "this section includes",
    "this document covers:",
    "this document includes",
)


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
        messages: list[ChatCompletionMessageParam] = [
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


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_multiline_text(text: str) -> str:
    lines = []
    for raw_line in str(text or "").splitlines():
        stripped = raw_line.rstrip()
        if not stripped.strip():
            continue
        leading_spaces = len(stripped) - len(stripped.lstrip(" "))
        compact = re.sub(r"\s+", " ", stripped.lstrip())
        lines.append((" " * leading_spaces) + compact)
    return "\n".join(lines).strip()


def _looks_like_title_enum(text: str) -> bool:
    normalized = _normalize_whitespace(text).lower()
    return any(normalized.startswith(prefix) for prefix in _TITLE_ENUM_PREFIXES)


def _truncate_navigation_summary(text: str, max_tokens: int = NAVIGATION_TOP_SUMMARY_MAX_TOKENS) -> str:
    """Truncate navigation summary while preserving multiline tree structure.

    Budget is measured in semantic tokens via ``count_cn_en`` (1 Chinese
    char = 1 token, 1 English word = 1 token) so the limit is
    language-fair.  For multiline tree previews, truncation removes
    trailing branches.  For single-line LLM summaries, the first
    sentence is kept; if still too long, ``truncate_text_by_tokens``
    is used (same middle-ellipsis strategy as layout_parser headings).
    """
    from shared.utils.text_utils import count_cn_en
    from app.services.common.kb_utils import truncate_text_by_tokens

    normalized = _normalize_multiline_text(text)
    if not normalized:
        return ""
    if count_cn_en(normalized) <= max_tokens:
        return normalized

    # Multiline content (tree preview) — truncate by keeping lines
    lines = normalized.split('\n')
    if len(lines) > 1:
        kept: List[str] = []
        current_tokens = 0
        for line in lines:
            line_tokens = count_cn_en(line)
            if kept and current_tokens + line_tokens > max_tokens:
                break
            kept.append(line)
            current_tokens += line_tokens
        if kept:
            return '\n'.join(kept)

    # Single-line content (LLM summary) — keep first sentence
    flat = _normalize_whitespace(normalized)
    sentences = re.split(r'(?<=[。！？；.!?;])\s+', flat)
    if sentences and sentences[0]:
        first = sentences[0]
        if count_cn_en(first) <= max_tokens:
            return first

    # Absolute fallback: token-aware truncation with middle '...'
    return truncate_text_by_tokens(flat, max_tokens, 0, lang_aware=False)


def _dedupe_summary_blocks(items: List[str]) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalize_multiline_text(item)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _resolve_document_tree(hierarchy: Dict[str, Any], file_name: str) -> Dict[str, Any]:
    content_keys = [k for k in hierarchy.keys() if k not in RESERVED_KEYS]
    fallback_tree: Dict[str, Any] | None = None
    for root_key in content_keys:
        subtree = hierarchy.get(root_key, {})
        if not isinstance(subtree, dict):
            continue
        if fallback_tree is None:
            fallback_tree = subtree
        if file_name in subtree and isinstance(subtree[file_name], dict):
            return subtree[file_name]
    return fallback_tree or hierarchy


def build_hierarchy_from_paths(paths: List[str]) -> Dict[str, Any]:
    """Rebuild a nested hierarchy tree from chunk paths."""
    root_dict: Dict[str, Any] = {}
    for path in paths:
        path_str = str(path or "").strip()
        if not path_str:
            continue
        nodes = [node.strip() for node in path_str.split("/") if node and node.strip()]
        current_dict = root_dict
        for node in nodes:
            if node not in current_dict or not isinstance(current_dict.get(node), dict):
                current_dict[node] = {}
            current_dict = current_dict[node]
    return root_dict


def ensure_hierarchy_json(
    file_dir: str,
    paths: List[str],
    *,
    overwrite: bool = False,
) -> str:
    """Materialize `hierarchy.json` from chunk paths when the parser did not emit one."""
    hierarchy_path = os.path.join(file_dir, "hierarchy.json")
    if os.path.exists(hierarchy_path) and not overwrite:
        return hierarchy_path

    hierarchy = build_hierarchy_from_paths(paths)
    if not hierarchy:
        return ""

    os.makedirs(file_dir, exist_ok=True)
    with open(hierarchy_path, "w", encoding="utf-8") as f:
        json.dump(hierarchy, f, ensure_ascii=False, indent=2)
    return hierarchy_path


def _truncate_tree_title(title: str) -> str:
    """Truncate an individual section title for tree preview display.

    Uses the same token-aware truncation as layout_parser headings:
    keeps start and end tokens with '...' in the middle.
    """
    from app.services.common.kb_utils import truncate_text_by_tokens

    return truncate_text_by_tokens(
        title,
        _TREE_TITLE_MAX_TOKENS_START,
        _TREE_TITLE_MAX_TOKENS_END,
        lang_aware=True,
    )


def _build_section_tree_preview(
    document_tree: Dict[str, Any],
    *,
    max_depth: int = NON_LLM_TOP_SUMMARY_MAX_DEPTH,
    max_items: int = NON_LLM_TOP_SUMMARY_MAX_SECTIONS,
) -> str:
    """BFS-based compact section tree preview.

    Excludes system placeholder nodes (Root, images, tables) and
    truncates individual long titles using token-aware heading truncation.
    """
    selected_paths: set[tuple[str, ...]] = set()
    queue = deque()
    collected = 0

    for key, subtree in document_tree.items():
        if key in RESERVED_KEYS or not isinstance(subtree, dict):
            continue
        normalized = _normalize_whitespace(key)
        if not normalized or normalized.lower() in _TREE_EXCLUDED_TITLES:
            continue
        queue.append(((normalized,), normalized, subtree, 1))

    while queue and collected < max_items:
        path, title, subtree, depth = queue.popleft()
        if title:
            selected_paths.add(path)
            collected += 1

        if depth >= max_depth:
            continue
        for child_key, child_subtree in subtree.items():
            if child_key in RESERVED_KEYS or not isinstance(child_subtree, dict):
                continue
            child_title = _normalize_whitespace(child_key)
            if not child_title or child_title.lower() in _TREE_EXCLUDED_TITLES:
                continue
            queue.append((path + (child_title,), child_title, child_subtree, depth + 1))

    lines: List[str] = []

    def _render(subtree: Dict[str, Any], depth: int, path_prefix: tuple[str, ...]) -> None:
        if depth > max_depth:
            return
        for key, child_subtree in subtree.items():
            if key in RESERVED_KEYS or not isinstance(child_subtree, dict):
                continue
            title = _normalize_whitespace(key)
            if not title or title.lower() in _TREE_EXCLUDED_TITLES:
                continue
            current_path = path_prefix + (title,)
            if current_path not in selected_paths:
                continue
            indent = "  " * (depth - 1)
            display_title = _truncate_tree_title(title)
            lines.append(f"{indent}- {display_title}")
            _render(child_subtree, depth + 1, current_path)

    _render(document_tree, 1, ())
    return "\n".join(lines)


def _build_navigation_top_summary(hierarchy: Dict[str, Any], file_name: str) -> str:
    """Build the navigation-facing top summary from enriched hierarchy.json.

    Strategy (aligned with production kb_tasks.py):
    - If root has a high-quality LLM-generated _summary → use it directly.
    - If _summary is missing or is a low-quality title-enum fallback →
      generate a depth-limited BFS tree preview instead.
    """
    document_tree = _resolve_document_tree(hierarchy, file_name)
    if not isinstance(document_tree, dict):
        return ""

    root_summary = _normalize_whitespace(document_tree.get(SUMMARY_KEY, ""))

    # High-quality LLM summary → use directly, no tree needed
    if root_summary and not _looks_like_title_enum(root_summary):
        return _truncate_navigation_summary(root_summary)

    # No summary or title-enum fallback → generate tree preview
    tree_preview = _build_section_tree_preview(
        document_tree,
        max_depth=NON_LLM_TOP_SUMMARY_MAX_DEPTH,
        max_items=NON_LLM_TOP_SUMMARY_MAX_SECTIONS,
    )
    if tree_preview:
        return _truncate_navigation_summary(
            "This document includes the following contents:\n" + tree_preview
        )
    return ""


# ─── Chunk Lookup ─────────────────────────────────────────────────────────────


def _build_chunk_lookup(
    chunks: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Build a mapping from the LAST path segment to a snippet string.

    For each chunk, compose a structured snippet:
      - If metadata.summary exists → use it directly
    - Otherwise → title (node_key) + keywords
    """
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
            snippet_parts = [node_key]
            if isinstance(meta, dict):
                kw = meta.get("keywords")
                if isinstance(kw, list):
                    kw_text = ", ".join(str(item).strip() for item in kw if str(item).strip())
                else:
                    kw_text = str(kw or "").strip()
                if kw_text:
                    snippet_parts.append(f"Keywords: {kw_text}")
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
      "This section covers: 第1章, 第2章, 第3章"

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
            (e.g. "This section covers: 第1章, 第2章"). Defaults to True.

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
    """Extract the top-level summary for a file from its enriched hierarchy.

    Delegates entirely to _build_navigation_top_summary which handles
    both LLM-generated summaries and tree-preview fallback.
    """
    return _build_navigation_top_summary(hierarchy, file_name)


def load_navigation_top_summary(file_dir: str, file_name: str) -> str:
    """Load hierarchy.json from a parsed file directory and extract navigation summary."""
    hierarchy_path = os.path.join(file_dir, "hierarchy.json")
    if not os.path.exists(hierarchy_path):
        return ""
    try:
        with open(hierarchy_path, "r", encoding="utf-8") as f:
            hierarchy = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read hierarchy for top_summary: dir={file_dir}, error={e}")
        return ""
    return _extract_top_summary(hierarchy, file_name)
