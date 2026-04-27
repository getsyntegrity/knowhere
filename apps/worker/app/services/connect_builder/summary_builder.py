"""
summary_builder: Bottom-up recursive summarization for document navigation.

Reads doc_nav.json + chunks.json for a file and generates ``summary`` fields
at every intermediate node via LLM aggregation.
The enriched doc_nav.json is written back to disk.

Usage (standalone):
    from app.services.connect_builder.summary_builder import enrich_doc_nav_summaries
    enrich_doc_nav_summaries(kb_dir, source_file="report.pdf")

Called by graph_builder.build_and_deploy() after file deploy, before KG build.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from shared.utils.text_utils import truncate_content_preview


# ─── Constants ────────────────────────────────────────────────────────────────

# Summary output max length for recursive LLM aggregation (≤100 chars per node)
SUMMARY_MAX_LEN = 100
# Navigation top-summary budget measured in semantic tokens (count_cn_en)
NAVIGATION_TOP_SUMMARY_MAX_TOKENS = 200
# TODO: revisit this cap after we collect more real-world prompt/token budget data.
NON_LLM_TOP_SUMMARY_MAX_SECTIONS = 20
NON_LLM_TOP_SUMMARY_MAX_DEPTH = 2

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


# ─── Chunk Lookup ───────────────────────────────────────────────────────────────────


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


#
# Uses explicit children arrays:
#   [{"title": "Section A", "summary": "...", "children": [{"title": "SubA1", ...}]}]
# ═══════════════════════════════════════════════════════════════════════════════


DOC_NAV_FILENAME = "doc_nav.json"


def _load_doc_nav(file_dir: str) -> Optional[Dict[str, Any]]:
    """Load doc_nav.json from a parsed file directory, return None if absent."""
    path = os.path.join(file_dir, DOC_NAV_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read {DOC_NAV_FILENAME}: dir={file_dir}, error={e}")
        return None


def _save_doc_nav(file_dir: str, doc_nav: Dict[str, Any]) -> None:
    """Write doc_nav.json back to disk."""
    path = os.path.join(file_dir, DOC_NAV_FILENAME)
    os.makedirs(file_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc_nav, f, ensure_ascii=False, indent=2)


def ensure_doc_nav_json(
    file_dir: str,
    chunks: List[Dict[str, Any]],
    source_file_name: str = "",
    *,
    overwrite: bool = False,
) -> str:
    """Materialize ``doc_nav.json`` from chunks when the parser did not emit one."""
    nav_path = os.path.join(file_dir, DOC_NAV_FILENAME)
    if os.path.exists(nav_path) and not overwrite:
        return nav_path

    # Re-use ZipResultService's builder to keep the format canonical
    from shared.services.storage.zip_result_service import ZipResultService
    svc = ZipResultService()
    doc_nav = svc._build_doc_nav(chunks, source_file_name)

    _save_doc_nav(file_dir, doc_nav)
    return nav_path


# ─── Recursive summarization on doc_nav sections ─────────────────────────────


def _recursive_summarize_nav(
    node: Dict[str, Any],
    chunk_lookup: Dict[str, str],
    use_llm: bool = True,
) -> str:
    """Bottom-up recursive summarization on a doc_nav section node.

    Operates on the children-array tree structure of doc_nav.json.

    For each node:
    - Leaf (children==[]) → keep existing summary (set during ZIP creation)
      or update from chunk_lookup if a better one exists.
    - Non-leaf → recursively summarize children, then aggregate.

    Writes summary in-place into ``node["summary"]``.
    Returns the summary string.
    """
    children = node.get("children", [])
    title = node.get("title", "")

    if not children:
        # Leaf node — check if chunk_lookup has a better summary
        existing = (node.get("summary") or "").strip()
        lookup_snippet = chunk_lookup.get(title, "")
        if lookup_snippet and (not existing or existing == title):
            node["summary"] = lookup_snippet
        return node.get("summary", "")

    # Recurse into children
    child_summaries: List[Tuple[str, str]] = []
    for child in children:
        child_summary = _recursive_summarize_nav(child, chunk_lookup, use_llm)
        if child_summary:
            child_summaries.append((child.get("title", ""), child_summary))

    if not child_summaries:
        return node.get("summary", "")

    # Aggregate child summaries
    aggregated_parts = []
    for name, summary in child_summaries:
        truncated = truncate_content_preview(summary, head=SUMMARY_MAX_LEN, tail=0)
        aggregated_parts.append(f"[{name}] {truncated}")

    aggregated_text = "\n".join(aggregated_parts)

    if len(child_summaries) <= 1:
        result = truncate_content_preview(child_summaries[0][1], head=SUMMARY_MAX_LEN, tail=0)
    else:
        titles = [name for name, _ in child_summaries]
        title_enum = "This section covers: " + ", ".join(titles)

        if not use_llm:
            result = title_enum
        else:
            total_len = sum(len(s) for _, s in child_summaries)
            if total_len > SUMMARY_MAX_LEN:
                result = _llm_summarize(aggregated_text, title)
                if not result:
                    result = title_enum
            else:
                result = title_enum

    node["summary"] = result
    return result


def _doc_nav_has_enriched_summaries(doc_nav: Dict[str, Any]) -> bool:
    """Check if enrichment has already been run on this doc_nav.

    Aligned with old _has_summaries logic for hierarchy.json:
    In doc_nav.json, leaf nodes already have summary from ZIP creation,
    so only non-leaf (parent) summaries are set by enrichment.
    We recursively check that ALL non-leaf nodes across all depths
    have a non-empty summary — if any is missing, enrichment is incomplete.
    """
    def _check_sections(sections: List[Dict[str, Any]]) -> bool:
        """Returns True if all non-leaf nodes in sections have summaries."""
        for section in sections:
            children = section.get("children", [])
            if not children:
                continue
            # This is a non-leaf node — must have summary from enrichment
            if not section.get("summary"):
                return False
            # Recurse into children to check deeper non-leaf nodes
            if not _check_sections(children):
                return False
        return True

    sections = doc_nav.get("sections", [])
    if not sections:
        return False
    # Must have at least one non-leaf to be considered enriched
    has_non_leaf = any(s.get("children") for s in sections)
    if not has_non_leaf:
        return False
    return _check_sections(sections)


def _build_nav_top_summary(doc_nav: Dict[str, Any]) -> str:
    """Build navigation-facing top summary from enriched doc_nav.json.

    Strategy:
    - If root section has a high-quality LLM summary → use it.
    - Otherwise → build a tree preview from section titles.
    """
    sections = doc_nav.get("sections", [])
    if not sections:
        return ""

    # Check for a root-level LLM summary (first section if it's 'Root')
    root_section = None
    content_sections = []
    for s in sections:
        if s.get("title", "").lower() == "root":
            root_section = s
        else:
            content_sections.append(s)

    # Try root summary first
    if root_section:
        root_summary = _normalize_whitespace(root_section.get("summary", ""))
        if root_summary and not _looks_like_title_enum(root_summary):
            return _truncate_navigation_summary(root_summary)

    # Build tree preview from section titles
    lines: List[str] = []
    excluded = {"root", "images", "tables"}

    def _render_sections(secs: List[Dict], depth: int = 0) -> None:
        for sec in secs:
            title = sec.get("title", "")
            if title.lower() in excluded:
                continue
            if len(lines) >= NON_LLM_TOP_SUMMARY_MAX_SECTIONS:
                break
            indent = "  " * depth
            display = _truncate_tree_title(title)
            lines.append(f"{indent}- {display}")
            if depth + 1 < NON_LLM_TOP_SUMMARY_MAX_DEPTH:
                _render_sections(sec.get("children", []), depth + 1)

    _render_sections(content_sections)

    if lines:
        tree_text = "This document includes the following contents:\n" + "\n".join(lines)
        return _truncate_navigation_summary(tree_text)
    return ""


def enrich_doc_nav_summaries(
    kb_dir: str,
    source_file: Optional[str] = None,
    force: bool = False,
    use_llm: bool = True,
) -> Dict[str, str]:
    """Enrich doc_nav.json with bottom-up recursive summaries.

    Args:
        kb_dir: Absolute path to the KB directory.
        source_file: If given, only process this file. Otherwise process all.
        force: If True, regenerate even if summaries already exist.
        use_llm: If True, use LLM for multi-child aggregation.

    Returns:
        Dict mapping file_name → top-level summary string.
    """
    results: Dict[str, str] = {}
    mode_label = "LLM" if use_llm else "title-concat"

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
        doc_nav = _load_doc_nav(file_dir)
        if doc_nav is None:
            logger.debug(f"No {DOC_NAV_FILENAME} for {file_name}, skipping")
            continue

        if not force and _doc_nav_has_enriched_summaries(doc_nav):
            logger.debug(f"Summaries already exist in {DOC_NAV_FILENAME} for {file_name}, skipping")
            results[file_name] = _build_nav_top_summary(doc_nav)
            continue

        # Load chunks for snippet lookup
        chunks_path = os.path.join(file_dir, "chunks.json")
        chunks: List[Dict[str, Any]] = []
        if os.path.exists(chunks_path):
            with open(chunks_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            chunks = data.get("chunks", [])

        chunk_lookup = _build_chunk_lookup(chunks)
        logger.info(
            f"📝 Enriching {DOC_NAV_FILENAME} summaries for {file_name} "
            f"({len(chunk_lookup)} leaf snippets, mode={mode_label})"
        )

        # Recursively summarize each top-level section
        for section in doc_nav.get("sections", []):
            _recursive_summarize_nav(section, chunk_lookup, use_llm=use_llm)

        _save_doc_nav(file_dir, doc_nav)
        logger.info(f"✅ doc_nav summaries saved for {file_name}")

        top_summary = _build_nav_top_summary(doc_nav)
        results[file_name] = top_summary

    return results


def load_nav_top_summary(file_dir: str, file_name: str = "") -> str:
    """Load doc_nav.json and extract the navigation top summary."""
    doc_nav = _load_doc_nav(file_dir)
    if doc_nav is not None:
        return _build_nav_top_summary(doc_nav)
    return ""


def build_section_summary_lookup(file_dir: str) -> Dict[str, str]:
    """Build a flat {section_path: summary} dict from all nodes in doc_nav.json.

    Keys use the DocumentSection.section_path format produced by
    ``section_path_from_chunk_path`` (strips kb_root + filename prefix,
    joins remaining parts with ``" / "``).

    Traverses the full section tree at all depths.  Used by the publication
    pipeline to backfill DocumentSection.summary rows.

    Args:
        file_dir: Absolute path to the file-level directory
                  (e.g. ~/.knowhere/{kb_id}/{source_file_name}/).

    Returns:
        Dict mapping section_path → summary string (empty dict on any error).
    """
    from shared.services.retrieval.lexical_text import section_path_from_chunk_path

    doc_nav = _load_doc_nav(file_dir)
    if doc_nav is None:
        return {}

    lookup: Dict[str, str] = {}

    def _walk(node: Dict[str, Any]) -> None:
        nav_path = node.get("path", "")
        summary = node.get("summary", "")
        if nav_path and summary:
            section_path = section_path_from_chunk_path(nav_path)
            if section_path and section_path != "Root":
                lookup[section_path] = summary
        for child in node.get("children", []):
            _walk(child)

    for section in doc_nav.get("sections", []):
        _walk(section)

    return lookup
