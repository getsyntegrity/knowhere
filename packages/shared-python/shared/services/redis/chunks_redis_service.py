"""
Chunks数据Redis服务
"""
import json
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from shared.services.redis.redis_service import RedisService
from shared.utils.chunk_refs import extract_chunk_refs

try:
    import pandas as pd
except ImportError:
    pd = None


class ChunksRedisService:
    """Chunks数据Redis服务"""

    def __init__(self, redis_service: RedisService):
        self.redis = redis_service

    def _dataframe_to_chunks(self, df) -> List[Dict[str, Any]]:
        """
        将DataFrame转换为chunks格式

        Args:
            df: pandas DataFrame，包含文档解析结果

        Returns:
            List[Dict]: chunks数据列表
        """
        if df is None or len(df) == 0:
            logger.warning("DataFrame为空，返回空chunks列表")
            return []

        logger.debug(f"开始转换DataFrame为chunks: DataFrame长度={len(df)}")

        # 辅助函数
        def safe_int(x):
            """安全转换为整数"""
            if pd is not None and pd.isna(x):
                return 0
            try:
                return int(float(x))
            except (ValueError, TypeError):
                return 0

        def safe_split_kws(kw):
            """安全分割关键词，过滤单字符（与 tokens 的 _is_meaningful_token 一致）"""
            if pd is not None and pd.isna(kw):
                return []
            kw_str = str(kw)
            # 支持多种分隔符：分号、逗号
            if ";" in kw_str:
                parts = [k.strip() for k in kw_str.split(";") if k.strip()]
            elif "," in kw_str:
                parts = [k.strip() for k in kw_str.split(",") if k.strip()]
            else:
                parts = [kw_str.strip()] if kw_str.strip() else []
            # 过滤单字符关键词（单个数字、汉字、字母无检索意义）
            return [k for k in parts if len(k) > 1]

        def safe_parse_tokens(raw):
            """解析 tokens 字段：保留 jieba 分词链为列表，兼容新旧格式。
            
            新格式：分号分隔 'word1;word2;word3'（与 keywords 列一致）
            旧格式：箭头分隔 'word1->word2->word3' 或 "['word1->word2->...']"
            """
            if raw is None or (pd is not None and pd.isna(raw)):
                return []
            raw_str = str(raw).strip()
            if not raw_str:
                return []
            # List-like string from DataFrame: "['w1;w2']" or "['w1->w2']"
            if raw_str.startswith("[") and raw_str.endswith("]"):
                inner = raw_str[1:-1].strip()
                if (inner.startswith("'") and inner.endswith("'")) or \
                   (inner.startswith('"') and inner.endswith('"')):
                    inner = inner[1:-1]
                raw_str = inner
            # Determine separator: semicolon (new) or arrow (legacy)
            if ";" in raw_str:
                return [t.strip() for t in raw_str.split(";") if t.strip()]
            if "->" in raw_str:
                return [t.strip() for t in raw_str.split("->") if t.strip()]
            return []

        def safe_parse_rels(type_val):
            """安全解析 intra-doc 关系 (图文表引用，来自 type 字段)"""
            rels = []
            type_is_valid = type_val and not (pd is not None and pd.isna(type_val))
            if type_is_valid:
                type_str = str(type_val)
                if "\n" in type_str:
                    lines = [line.strip() for line in type_str.split("\n") if line.strip()]
                    rels.extend([line for line in lines[1:] if line.upper() != "PTXT"])
            return rels if rels else []

        def normalize_resource_ref(ref: Any) -> str:
            """标准化资源引用，去掉 chunk ref 包裹符号。"""
            ref_str = str(ref or "").strip()
            if ref_str.startswith("[") and ref_str.endswith("]"):
                ref_str = ref_str[1:-1].strip()
            return ref_str

        def parse_connect_to(connects):
            """解析 connectto 字段为 cross-chunk 关系列表"""
            if not connects or (pd is not None and pd.isna(connects)):
                return []
            if isinstance(connects, list):
                return connects
            connects_str = str(connects).strip()
            if not connects_str:
                return []
            if connects_str.startswith("["):
                try:
                    parsed = json.loads(connects_str)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return [{"target": connects_str, "relation": "related", "score": 1.0, "keywords": []}]

        def build_resource_target_map(chunk_list: List[Dict[str, Any]]) -> Dict[str, str]:
            """Build ref/path -> chunk_id aliases for image and table chunks."""
            target_map: Dict[str, str] = {}
            for item in chunk_list:
                if item.get("type") not in {"image", "table"}:
                    continue
                item_id = str(item.get("chunk_id") or item.get("know_id") or "").strip()
                if not item_id:
                    continue
                metadata = item.get("metadata", {})
                file_path = ""
                if isinstance(metadata, dict):
                    file_path = str(metadata.get("file_path") or "").strip()
                path_alias = str(item.get("path") or "").strip()
                aliases = {file_path, path_alias}
                for alias in list(aliases):
                    if alias:
                        aliases.add(f"[{alias}]")
                for alias in aliases:
                    if alias:
                        target_map[alias] = item_id
            return target_map

        def refs_to_embed_connections(refs: List[str], target_map: Dict[str, str]) -> List[Dict[str, Any]]:
            """Convert resource refs to connect_to embeds entries."""
            connections: List[Dict[str, Any]] = []
            for ref in refs:
                ref_str = str(ref or "").strip()
                if not ref_str:
                    continue
                target_id = target_map.get(ref_str)
                if not target_id and ref_str.startswith("[") and ref_str.endswith("]"):
                    target_id = target_map.get(ref_str[1:-1].strip())
                if not target_id:
                    continue
                connections.append({
                    "target": target_id,
                    "relation": "embeds",
                    "ref": ref_str,
                })
            return connections

        def merge_connections(*connection_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            """Merge connect_to entries while keeping stable order."""
            merged: List[Dict[str, Any]] = []
            seen = set()
            for connection_list in connection_lists:
                for item in connection_list or []:
                    if not isinstance(item, dict):
                        continue
                    key = (
                        str(item.get("target") or ""),
                        str(item.get("relation") or "related"),
                        str(item.get("ref") or ""),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(item)
            return merged

        chunks = []
        for i, (_, row) in enumerate(df.iterrows()):
            know_id = row.get("know_id")
            if know_id and not (pd is not None and pd.isna(know_id)):
                chunk_id = str(know_id)
            else:
                chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.uuid4())))
            content = str(row.get("content", ""))
            path = str(row.get("path", ""))
            type_val = row.get("type", "")

            if isinstance(type_val, str):
                normalized_type = type_val.strip().split("\n", 1)[0].lower()
                if normalized_type == "ptxt":
                    chunk_type = "text"
                elif normalized_type == "image":
                    chunk_type = "image"
                elif normalized_type == "table":
                    chunk_type = "table"
                else:
                    chunk_type = "text"
            else:
                chunk_type = "text"

            # 构建metadata
            relationship_refs = safe_parse_rels(type_val) or extract_chunk_refs(content)
            metadata = {
                "keywords": safe_split_kws(row.get("keywords")),
                "summary": str(row.get("summary", "")),
                "length": safe_int(row.get("length")) or len(content),
                "tokens": safe_parse_tokens(row.get("tokens")),
                "connect_to": parse_connect_to(row.get("connectto")),
            }
            metadata["_relationship_refs"] = relationship_refs

            # 解析 page_nums: "3,4" → [3, 4]
            raw_page_nums = row.get("page_nums", "")
            if raw_page_nums and not (pd is not None and pd.isna(raw_page_nums)):
                try:
                    page_nums_list = [int(p.strip()) for p in str(raw_page_nums).split(",") if p.strip()]
                except (ValueError, TypeError):
                    page_nums_list = []
            else:
                page_nums_list = []
            metadata["page_nums"] = page_nums_list

            # 根据类型添加特定字段
            if chunk_type == "image":
                image_ref = ""
                for ref in relationship_refs:
                    normalized_ref = normalize_resource_ref(ref)
                    if normalized_ref.lower().startswith("images/"):
                        image_ref = normalized_ref
                        break

                if image_ref:
                    img_name = image_ref.split("/", 1)[1]
                    metadata["file_path"] = image_ref
                    metadata["original_name"] = img_name
                else:
                    img_name = path.split("/")[-1] if path else f"image_{chunk_id}.jpg"
                    # Ensure image file name has an extension (atlas paths lack one)
                    if not any(img_name.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
                        img_name += ".png"
                    metadata["file_path"] = f"images/{img_name}"
                    metadata["original_name"] = img_name
            elif chunk_type == "table":
                tbl_name = (
                    path.split("/")[-1] if "/" in path else f"table_{chunk_id}.html"
                )
                metadata["file_path"] = f"tables/{tbl_name}"

            # 构建chunk对象
            chunk = {
                "chunk_id": chunk_id,
                "type": chunk_type,
                "content": content,
                "path": path,
                "metadata": metadata,
                # 兼容性字段（用于内部处理）
                "text": content,
                "order": i,
                "know_id": str(know_id),
                "keywords": metadata["keywords"],
                "summary": metadata["summary"],
                "tokens": metadata["tokens"],
            }

            chunks.append(chunk)

        resource_target_map = build_resource_target_map(chunks)
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            if not isinstance(metadata, dict):
                continue
            relationship_refs = metadata.pop("_relationship_refs", [])
            if chunk.get("type") != "text":
                continue
            embed_connections = refs_to_embed_connections(relationship_refs, resource_target_map)
            metadata["connect_to"] = merge_connections(
                embed_connections,
                metadata.get("connect_to", []),
            )

        logger.debug(f"DataFrame转换完成: chunks数量={len(chunks)}")
        return chunks

    async def save_dataframe_as_chunks(self, job_id: str, df) -> bool:
        """将DataFrame转换为chunks并保存到Redis"""
        try:
            chunks = self._dataframe_to_chunks(df)
            return await self.save_chunks(job_id, chunks)
        except Exception as e:
            logger.error(f"保存DataFrame为chunks失败: job_id={job_id}, error={e}")
            return False

    async def save_chunks(self, job_id: str, chunks: List[Dict[str, Any]]) -> bool:
        """保存chunks数据到Redis"""
        try:
            chunks_key = f"job_chunks:{job_id}"
            await self.redis.set(
                chunks_key,
                chunks,
                ttl=3600  # 1小时过期
            )
            logger.debug(f"Chunks数据保存成功: job_id={job_id}, count={len(chunks)}")
            return True
        except Exception as e:
            logger.error(f"保存chunks数据失败: job_id={job_id}, error={e}")
            return False

    async def get_chunks(self, job_id: str) -> Optional[List[Dict[str, Any]]]:
        """从Redis获取chunks数据"""
        try:
            chunks_key = f"job_chunks:{job_id}"
            chunks = await self.redis.get(chunks_key)
            if chunks:
                logger.debug(f"Chunks数据获取成功: job_id={job_id}, count={len(chunks)}")
            else:
                logger.warning(f"Chunks数据不存在: job_id={job_id}")
            return chunks
        except Exception as e:
            logger.error(f"获取chunks数据失败: job_id={job_id}, error={e}")
            return None

    async def delete_chunks(self, job_id: str) -> bool:
        """删除chunks数据"""
        try:
            chunks_key = f"job_chunks:{job_id}"
            await self.redis.delete(chunks_key)
            logger.debug(f"Chunks数据删除成功: job_id={job_id}")
            return True
        except Exception as e:
            logger.error(f"删除chunks数据失败: job_id={job_id}, error={e}")
            return False
