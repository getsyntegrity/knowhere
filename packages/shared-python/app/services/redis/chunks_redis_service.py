"""
Chunks数据Redis服务
"""
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from app.services.redis.redis_service import RedisService

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
        
        # 直接转换为字典数组
        chunks = df.to_dict('records')
        
        # 清理NaN值并添加必要字段映射
        for i, chunk in enumerate(chunks):
            # 清理NaN值
            for key, value in chunk.items():
                if pd is not None and pd.isna(value):
                    chunk[key] = None
            
            # 添加必要的字段映射
            chunk['chunk_id'] = str(chunk.get('know_id', uuid.uuid4()))
            chunk['text'] = chunk.pop('content', '')
            chunk['order'] = i
            
            # 确保keywords是列表格式
            keywords = chunk.get('keywords', [])
            if isinstance(keywords, str):
                try:
                    import json
                    keywords = json.loads(keywords)
                    if not isinstance(keywords, list):
                        keywords = [keywords]
                except (json.JSONDecodeError, TypeError):
                    keywords = [kw.strip() for kw in keywords.split(",") if kw.strip()]
            elif not isinstance(keywords, list):
                keywords = []
            chunk['keywords'] = keywords
            
            # 确保tokens是数字
            tokens = chunk.get('tokens', 0)
            if isinstance(tokens, str) and tokens.isdigit():
                tokens = int(tokens)
            elif not isinstance(tokens, (int, float)):
                tokens = 0
            chunk['tokens'] = tokens
        
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
