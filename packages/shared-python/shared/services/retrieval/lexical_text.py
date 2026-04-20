"""
Lexical text builders for canonical retrieval publication.
"""
from __future__ import annotations

from typing import Any, Optional

from shared.utils.text_utils import tokenize2stw_remove


def build_lexical_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    tokens = tokenize2stw_remove([text], stopwords=[], link_char=" ")
    token_text = tokens[0] if tokens else ""
    lexical_parts = [part for part in [text, token_text] if part]
    return "\n".join(lexical_parts) if lexical_parts else text


def build_content_lexical_text(chunk: dict[str, Any]) -> Optional[str]:
    content = str(chunk.get("content") or chunk.get("text") or "").strip()
    if not content:
        return None
    metadata = chunk.get("metadata") or {}
    tokens = metadata.get("tokens") if isinstance(metadata, dict) else None
    if isinstance(tokens, list):
        token_text = " ".join(str(token).strip() for token in tokens if str(token).strip())
    else:
        token_text = ""
    lexical_parts = [part for part in [content, token_text] if part]
    return "\n".join(lexical_parts) if lexical_parts else content


def section_path_from_chunk_path(source_path: Optional[str], *, separator: str = "/") -> str:
    if not source_path:
        return "Root"
    parts = [part.strip() for part in source_path.split(separator) if part.strip()]
    # parts[0] is the kb_dir (e.g. "Default_Root"), parts[1] is the filename — skip both
    if len(parts) <= 2:
        return "Root"
    section_parts = parts[2:]
    return " / ".join(section_parts) or "Root"


def build_path_lexical_text(source_path: Optional[str]) -> Optional[str]:
    section_path = section_path_from_chunk_path(source_path)
    if not section_path:
        return None
    normalized_path = section_path.replace(" / ", " ")
    return build_lexical_text(normalized_path)
