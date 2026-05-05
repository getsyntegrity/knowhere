"""
Database health API endpoints.
"""

from fastapi import APIRouter

from shared.core.database import (
    get_database_performance,
    prewarm_connection_pool,
)

router = APIRouter()


@router.get("/database/performance")
async def get_database_performance_stats():
    """Return database performance statistics."""
    return await get_database_performance()


@router.post("/database/prewarm")
async def prewarm_database_connections():
    """Prewarm the database connection pool."""
    await prewarm_connection_pool()
    return {"message": "Database connection pool prewarming completed"}
