"""
API路由总入口
"""
from fastapi import APIRouter
from app.api.v1.api_v1 import api_router as v1_router

api_router = APIRouter()

# 注册v1路由
api_router.include_router(v1_router, prefix="/v1")

__all__ = ["api_router"]
