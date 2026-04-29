"""Convert parser DataFrames into canonical chunk payloads."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Dict, Literal, Protocol, TypeAlias, TypedDict, Union, cast

import pandas as pd
from loguru import logger

from shared.utils.chunk_refs import ChunkRefSpan, extract_chunk_ref_spans


class _ParserRow(Protocol):
    def get(self, key: str, default: object = ...) -> object: ...


class _ParserDataFrame(Protocol):
    def __len__(self) -> int: ...

    def iterrows(self) -> Iterable[tuple[object, _ParserRow]]: ...


class PositionPayload(TypedDict):
    start: int
    end: int


class ConnectionPayload(TypedDict, total=False):
    target: str
    relation: str
    ref: str
    position: PositionPayload
    score: float
    keywords: list[str]


JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = Union[
    JsonPrimitive,
    list["JsonValue"],
    dict[str, "JsonValue"],
]
RelationshipRef: TypeAlias = str | ChunkRefSpan
ConnectionValue: TypeAlias = str | ConnectionPayload
ChunkType: TypeAlias = Literal["text", "image", "table"]


class ChunkMetadata(TypedDict, total=False):
    keywords: list[str]
    summary: str
    length: int
    tokens: list[str]
    connect_to: list[ConnectionValue]
    page_nums: list[int]
    file_path: str
    original_name: str
    _relationship_refs: list[RelationshipRef]


class ChunkPayload(TypedDict):
    chunk_id: str
    type: ChunkType
    content: str
    path: str
    metadata: ChunkMetadata
    text: str
    order: int
    know_id: str
    keywords: list[str]
    summary: str
    tokens: list[str]


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    try:
        return bool(result)
    except (TypeError, ValueError):
        return False


def _safe_int(value: object) -> int:
    if _is_missing(value):
        return 0
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return 0


def _safe_split_keywords(value: object) -> list[str]:
    if _is_missing(value):
        return []
    keyword_text = str(value)
    if ";" in keyword_text:
        keywords = [
            keyword.strip() for keyword in keyword_text.split(";") if keyword.strip()
        ]
    elif "," in keyword_text:
        keywords = [
            keyword.strip() for keyword in keyword_text.split(",") if keyword.strip()
        ]
    else:
        keywords = [keyword_text.strip()] if keyword_text.strip() else []
    return [keyword for keyword in keywords if len(keyword) > 1]


def _safe_parse_tokens(value: object) -> list[str]:
    if _is_missing(value):
        return []
    token_text = str(value).strip()
    if not token_text:
        return []
    if token_text.startswith("[") and token_text.endswith("]"):
        inner_text = token_text[1:-1].strip()
        if (inner_text.startswith("'") and inner_text.endswith("'")) or (
            inner_text.startswith('"') and inner_text.endswith('"')
        ):
            inner_text = inner_text[1:-1]
        token_text = inner_text
    if ";" in token_text:
        return [token.strip() for token in token_text.split(";") if token.strip()]
    if "->" in token_text:
        return [token.strip() for token in token_text.split("->") if token.strip()]
    return []


def _safe_parse_relationships(value: object) -> list[str]:
    if _is_missing(value):
        return []
    if not isinstance(value, str) or "\n" not in value:
        return []
    lines = [line.strip() for line in value.split("\n") if line.strip()]
    return [line for line in lines[1:] if line.upper() != "PTXT"]


def _normalize_resource_ref(ref: RelationshipRef) -> str:
    if isinstance(ref, dict):
        ref_text = str(ref.get("ref") or "").strip()
    else:
        ref_text = str(ref or "").strip()
    if ref_text.startswith("[") and ref_text.endswith("]"):
        ref_text = ref_text[1:-1].strip()
    return ref_text


def _find_embedded_resource_path(
    refs: Sequence[RelationshipRef], resource_dir: str
) -> str:
    resource_prefix = f"{resource_dir}/"
    for ref in refs:
        normalized_ref = _normalize_resource_ref(ref)
        if normalized_ref.startswith(resource_prefix):
            return normalized_ref
    return ""


def _parse_connect_to(value: object) -> list[ConnectionValue]:
    if not value or _is_missing(value):
        return []
    if isinstance(value, list):
        return [
            cast(ConnectionValue, item)
            for item in value
            if isinstance(item, str) or isinstance(item, dict)
        ]
    connects_text = str(value).strip()
    if not connects_text:
        return []
    if connects_text.startswith("["):
        try:
            parsed: object = json.loads(connects_text)
            if isinstance(parsed, list):
                return [
                    cast(ConnectionValue, item)
                    for item in parsed
                    if isinstance(item, str) or isinstance(item, dict)
                ]
        except json.JSONDecodeError:
            pass
    return [
        {
            "target": connects_text,
            "relation": "related",
            "score": 1.0,
            "keywords": [],
        }
    ]


def _build_resource_target_map(chunks: Sequence[ChunkPayload]) -> dict[str, str]:
    target_map: dict[str, str] = {}
    for chunk in chunks:
        if chunk["type"] not in {"image", "table"}:
            continue
        chunk_id = str(chunk["chunk_id"] or chunk["know_id"]).strip()
        if not chunk_id:
            continue
        metadata = chunk["metadata"]
        file_path = ""
        file_path = str(metadata.get("file_path") or "").strip()
        path_alias = chunk["path"].strip()
        aliases = {file_path, path_alias}
        for alias in list(aliases):
            if alias:
                aliases.add(f"[{alias}]")
        for alias in aliases:
            if alias:
                target_map[alias] = chunk_id
    return target_map


def _refs_to_embed_connections(
    refs: Sequence[RelationshipRef], target_map: Mapping[str, str]
) -> list[ConnectionPayload]:
    connections: list[ConnectionPayload] = []
    for ref in refs:
        if isinstance(ref, dict):
            ref_text = str(ref.get("ref") or "").strip()
            start = ref.get("start")
            end = ref.get("end")
        else:
            ref_text = str(ref or "").strip()
            start = None
            end = None
        if not ref_text:
            continue
        target_id = target_map.get(ref_text)
        if not target_id and ref_text.startswith("[") and ref_text.endswith("]"):
            target_id = target_map.get(ref_text[1:-1].strip())
        if not target_id:
            continue
        connection: ConnectionPayload = {
            "target": target_id,
            "relation": "embeds",
            "ref": ref_text,
        }
        if isinstance(start, int) and isinstance(end, int):
            connection["position"] = {
                "start": start,
                "end": end,
            }
        connections.append(connection)
    return connections


def _merge_connections(
    *connection_lists: Sequence[ConnectionValue],
) -> list[ConnectionValue]:
    merged: list[ConnectionValue] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for connection_list in connection_lists:
        for item in connection_list or []:
            if not isinstance(item, dict):
                continue
            position = item.get("position")
            position_data = position if isinstance(position, dict) else {}
            key = (
                str(item.get("target") or ""),
                str(item.get("relation") or "related"),
                str(item.get("ref") or ""),
                str(position_data.get("start", "")),
                str(position_data.get("end", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _parse_page_numbers(value: object) -> list[int]:
    if _is_missing(value):
        return []
    try:
        return [
            int(page_number.strip())
            for page_number in str(value).split(",")
            if page_number.strip()
        ]
    except (ValueError, TypeError):
        return []


def _get_chunk_type(value: object) -> ChunkType:
    if not isinstance(value, str):
        return "text"
    normalized_type = value.strip().split("\n", 1)[0].lower()
    if normalized_type == "ptxt":
        return "text"
    if normalized_type == "image":
        return "image"
    if normalized_type == "table":
        return "table"
    return "text"


def _get_relationship_refs(type_value: object, content: str) -> list[RelationshipRef]:
    parsed_relationships = _safe_parse_relationships(type_value)
    if parsed_relationships:
        return [relationship for relationship in parsed_relationships]
    return [span for span in extract_chunk_ref_spans(content)]


def _get_connect_to(metadata: ChunkMetadata) -> list[ConnectionValue]:
    connect_to = metadata.get("connect_to")
    return connect_to if isinstance(connect_to, list) else []


def dataframe_to_chunks(df: _ParserDataFrame | None) -> list[Dict[str, JsonValue]]:
    """Convert a parser DataFrame into chunk records."""
    if df is None or len(df) == 0:
        logger.warning("DataFrame is empty; returning an empty chunks list")
        return []

    logger.debug(f"Converting DataFrame to chunks: length={len(df)}")

    chunks: list[ChunkPayload] = []
    for index, (_, row) in enumerate(df.iterrows()):
        know_id = row.get("know_id")
        if know_id and not _is_missing(know_id):
            chunk_id = str(know_id)
        else:
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.uuid4())))

        content = str(row.get("content", ""))
        path = str(row.get("path", ""))
        type_value = row.get("type", "")
        chunk_type = _get_chunk_type(type_value)
        relationship_refs = _get_relationship_refs(type_value, content)

        metadata: ChunkMetadata = {
            "keywords": _safe_split_keywords(row.get("keywords")),
            "summary": str(row.get("summary", "")),
            "length": _safe_int(row.get("length")) or len(content),
            "tokens": _safe_parse_tokens(row.get("tokens")),
            "connect_to": _parse_connect_to(row.get("connectto")),
            "_relationship_refs": relationship_refs,
            "page_nums": _parse_page_numbers(row.get("page_nums", "")),
        }

        if chunk_type == "image":
            embedded_image_path = _find_embedded_resource_path(
                relationship_refs, "images"
            )
            if embedded_image_path:
                image_name = os.path.basename(embedded_image_path)
                metadata["file_path"] = embedded_image_path
                metadata["original_name"] = image_name
            else:
                normalized_path = path.replace("-->", "/")
                image_name = (
                    os.path.basename(normalized_path)
                    if normalized_path
                    else f"image_{chunk_id}.jpg"
                )
                _, image_extension = os.path.splitext(image_name)
                if not image_extension:
                    image_name += ".png"
                metadata["file_path"] = f"images/{image_name}"
                metadata["original_name"] = image_name
        elif chunk_type == "table":
            embedded_table_path = _find_embedded_resource_path(
                relationship_refs, "tables"
            )
            if embedded_table_path:
                metadata["file_path"] = embedded_table_path
            else:
                normalized_path = path.replace("-->", "/")
                table_name = (
                    os.path.basename(normalized_path)
                    if normalized_path
                    else f"table_{chunk_id}.html"
                )
                metadata["file_path"] = f"tables/{table_name}"

        chunks.append(
            {
                "chunk_id": chunk_id,
                "type": chunk_type,
                "content": content,
                "path": path,
                "metadata": metadata,
                "text": content,
                "order": index,
                "know_id": str(know_id),
                "keywords": metadata["keywords"],
                "summary": metadata["summary"],
                "tokens": metadata["tokens"],
            }
        )

    resource_target_map = _build_resource_target_map(chunks)
    for chunk in chunks:
        metadata = chunk["metadata"]
        relationship_refs = metadata.pop("_relationship_refs", [])
        if chunk["type"] != "text":
            continue
        embed_connections = _refs_to_embed_connections(
            relationship_refs, resource_target_map
        )
        metadata["connect_to"] = _merge_connections(
            embed_connections,
            _get_connect_to(metadata),
        )

    logger.debug(f"DataFrame conversion completed: chunk count={len(chunks)}")
    return cast(list[Dict[str, JsonValue]], chunks)
