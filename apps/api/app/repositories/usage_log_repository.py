"""
使用日志数据访问层
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.models.database.usage_log import UsageLog
from app.repositories.base_repository import BaseRepository
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class UsageLogRepository(BaseRepository[UsageLog, dict, dict]):
    """使用日志数据访问"""
    
    def __init__(self):
        super().__init__(UsageLog)
    
    async def get_by_user_id(self, session: AsyncSession, user_id: str, limit: int = 100) -> List[UsageLog]:
        """获取用户的使用日志"""
        result = await session.execute(
            select(UsageLog)
            .where(UsageLog.user_id == user_id)
            .order_by(UsageLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    async def get_by_api_key_id(self, session: AsyncSession, api_key_id: str, limit: int = 100) -> List[UsageLog]:
        """根据API Key获取使用日志"""
        result = await session.execute(
            select(UsageLog)
            .where(UsageLog.api_key_id == api_key_id)
            .order_by(UsageLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    async def get_usage_stats(self, session: AsyncSession, user_id: str, period: str = "month") -> Dict[str, Any]:
        """获取使用统计"""
        # 计算时间范围
        now = datetime.utcnow()
        if period == "day":
            start_date = now - timedelta(days=1)
        elif period == "week":
            start_date = now - timedelta(weeks=1)
        elif period == "month":
            start_date = now - timedelta(days=30)
        elif period == "year":
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=30)
        
        # 查询总体统计
        stats_result = await session.execute(
            select(
                func.count(UsageLog.id).label("total_calls"),
                func.sum(UsageLog.credits_used).label("total_credits_used"),
                func.avg(UsageLog.response_time).label("avg_response_time"),
                func.count(UsageLog.id).filter(UsageLog.status_code.between(200, 299)).label("success_calls"),
                func.count(UsageLog.id).filter(UsageLog.status_code >= 400).label("error_calls")
            )
            .where(UsageLog.user_id == user_id)
            .where(UsageLog.created_at >= start_date)
        )
        
        stats = stats_result.first()
        
        # 查询热门端点
        endpoint_result = await session.execute(
            select(
                UsageLog.endpoint,
                func.count(UsageLog.id).label("call_count"),
                func.sum(UsageLog.credits_used).label("credits_used")
            )
            .where(UsageLog.user_id == user_id)
            .where(UsageLog.created_at >= start_date)
            .group_by(UsageLog.endpoint)
            .order_by(desc("call_count"))
            .limit(10)
        )
        
        top_endpoints = [
            {
                "endpoint": row.endpoint,
                "call_count": row.call_count,
                "credits_used": row.credits_used
            }
            for row in endpoint_result
        ]
        
        # 计算成功率
        total_calls = stats.total_calls or 0
        success_calls = stats.success_calls or 0
        success_rate = (success_calls / total_calls * 100) if total_calls > 0 else 0
        
        return {
            "period": period,
            "total_calls": total_calls,
            "total_credits_used": stats.total_credits_used or 0,
            "avg_response_time": float(stats.avg_response_time or 0),
            "success_rate": round(success_rate, 2),
            "error_calls": stats.error_calls or 0,
            "top_endpoints": top_endpoints,
            "start_date": start_date,
            "end_date": now
        }
    
    async def get_daily_usage(self, session: AsyncSession, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """获取每日使用统计"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        result = await session.execute(
            select(
                func.date(UsageLog.created_at).label("date"),
                func.count(UsageLog.id).label("call_count"),
                func.sum(UsageLog.credits_used).label("credits_used")
            )
            .where(UsageLog.user_id == user_id)
            .where(UsageLog.created_at >= start_date)
            .group_by(func.date(UsageLog.created_at))
            .order_by("date")
        )
        
        return [
            {
                "date": row.date.isoformat(),
                "call_count": row.call_count,
                "credits_used": row.credits_used
            }
            for row in result
        ]
    
    async def get_by_endpoint(self, session: AsyncSession, user_id: str, endpoint: str, limit: int = 100) -> List[UsageLog]:
        """根据端点获取使用日志"""
        result = await session.execute(
            select(UsageLog)
            .where(UsageLog.user_id == user_id)
            .where(UsageLog.endpoint == endpoint)
            .order_by(UsageLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
