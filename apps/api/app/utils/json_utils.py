"""
JSON 序列化辅助工具
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Mapping, MutableSet


def make_json_safe(value: Any, *, max_preview_rows: int = 5, _visited: MutableSet[int] | None = None) -> Any:
    """
    将复杂对象转换为可 JSON 序列化的结构，避免常见类型（DataFrame、ndarray 等）导致的序列化失败。

    Args:
        value: 待转换的对象
        max_preview_rows: DataFrame 等对象预览的最大行数
        _visited: 内部使用，避免循环引用

    Returns:
        可 JSON 序列化的数据结构
    """
    if _visited is None:
        _visited = set()

    basic_types = (str, int, float, bool, type(None))
    if isinstance(value, basic_types):
        return value

    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    obj_id = id(value)
    if obj_id in _visited:
        return "<recursive_reference>"
    _visited.add(obj_id)

    try:
        import numpy as np  # type: ignore
    except Exception:  # pragma: no cover
        np = None  # type: ignore

    if np is not None:
        if isinstance(value, np.generic):
            _visited.discard(obj_id)
            return value.item()
        if isinstance(value, np.ndarray):
            _visited.discard(obj_id)
            return {
                "__type__": "ndarray",
                "shape": value.shape,
                "dtype": str(value.dtype),
            }

    try:
        import pandas as pd  # type: ignore
    except Exception:  # pragma: no cover
        pd = None  # type: ignore

    if pd is not None:
        if isinstance(value, pd.DataFrame):
            preview = value.head(max_preview_rows).to_dict(orient="records")
            _visited.discard(obj_id)
            return {
                "__type__": "DataFrame",
                "rows": int(len(value)),
                "columns": list(map(str, value.columns)),
                "preview": preview,
            }
        if isinstance(value, pd.Series):
            preview = value.head(max_preview_rows).to_dict()
            _visited.discard(obj_id)
            return {
                "__type__": "Series",
                "length": int(len(value)),
                "preview": preview,
            }

    if isinstance(value, Mapping):
        serialized = {str(key): make_json_safe(val, max_preview_rows=max_preview_rows, _visited=_visited) for key, val in value.items()}
        _visited.discard(obj_id)
        return serialized

    if isinstance(value, (list, tuple, set, frozenset)):
        serialized_seq = [make_json_safe(item, max_preview_rows=max_preview_rows, _visited=_visited) for item in value]
        _visited.discard(obj_id)
        return serialized_seq

    if hasattr(value, "__dict__"):
        serialized = {str(key): make_json_safe(val, max_preview_rows=max_preview_rows, _visited=_visited) for key, val in vars(value).items()}
        serialized["__type__"] = value.__class__.__name__
        _visited.discard(obj_id)
        return serialized

    _visited.discard(obj_id)
    return str(value)
