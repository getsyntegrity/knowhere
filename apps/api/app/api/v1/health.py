"""
数据库健康检查API端点
"""
from shared.core.database import (get_database_health, get_database_info,
                               get_database_performance,
                               prewarm_connection_pool)
from fastapi import APIRouter

router = APIRouter()

@router.get("/database/health")
async def check_database_health():
    """检查数据库健康状态"""
    return await get_database_health()

@router.get("/database/info")
async def get_database_information():
    """获取数据库信息"""
    return await get_database_info()

@router.get("/database/performance")
async def get_database_performance_stats():
    """获取数据库性能统计"""
    return await get_database_performance()

@router.post("/database/prewarm")
async def prewarm_database_connections():
    """预热数据库连接池"""
    await prewarm_connection_pool()
    return {"message": "Database connection pool prewarming completed"}
