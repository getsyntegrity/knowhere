"""
Chunks数据Redis服务
"""
import json
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from shared.services.redis.redis_service import RedisService

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
                    lines = type_str.split("\n")[1:-1]
                    rels.extend([line.strip() for line in lines if line.strip()])
            return rels if rels else []

        def parse_connect_to(connects):
            """解析 connectto 字段为 cross-chunk 关系列表"""
            if not connects or (pd is not None and pd.isna(connects)):
                return []
            connects_str = str(connects).strip()
            if not connects_str:
                return []
            # JSON array format (new)
            if connects_str.startswith("["):
                try:
                    parsed = json.loads(connects_str)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            # Legacy: newline-separated chunk IDs
            if "\n" in connects_str:
                lines = [line.strip() for line in connects_str.split("\n") if line.strip()]
                return [{"target": line, "relation": "related", "score": 1.0, "keywords": []} for line in lines]
            # Legacy: single value
            return [{"target": connects_str, "relation": "related", "score": 1.0, "keywords": []}]

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
                if type_val.startswith("PTXT"):
                    chunk_type = "text"
                elif type_val.startswith("IMAGE_"):
                    chunk_type = "image"
                elif type_val.startswith("TABLE_"):
                    chunk_type = "table"
                else:
                    chunk_type = "text"
            else:
                chunk_type = "text"

            # 构建metadata
            metadata = {
                "keywords": safe_split_kws(row.get("keywords")),
                "summary": str(row.get("summary", "")),
                "length": safe_int(row.get("length")) or len(content),
                "tokens": safe_parse_tokens(row.get("tokens")),
                "relationships": safe_parse_rels(type_val),
                "connect_to": parse_connect_to(row.get("connectto")),
            }

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
                img_name = (
                    path.split("/")[-1] if "/" in path else f"image_{chunk_id}.jpg"
                )
                # Ensure image file name has an extension (atlas paths lack one)
                if not any(img_name.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    img_name += ".png"
                metadata["file_path"] = f"images/{img_name}"
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
