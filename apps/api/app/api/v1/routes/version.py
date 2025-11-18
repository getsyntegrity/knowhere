"""
版本信息API端点
"""
import os
from datetime import datetime
from fastapi import APIRouter
from shared.core.config import app_config

router = APIRouter()


@router.get("/version", summary="获取应用版本信息")
async def get_version():
    """
    获取当前部署的版本信息
    
    返回格式：
    {
        "version": "v1.0.0",
        "commit": "abc1234",
        "build_time": "2024-01-01T00:00:00Z",
        "environment": "production"
    }
    """
    # 从环境变量获取版本信息
    version = os.getenv("APP_VERSION", app_config.APP_VERSION)
    commit = os.getenv("GIT_COMMIT", "")
    build_time = os.getenv("BUILD_TIME", "")
    environment = os.getenv("ENVIRONMENT", "development")
    
    return {
        "version": version,
        "commit": commit,
        "build_time": build_time,
        "environment": environment,
        "service": "knowhere-api"
    }


@router.get("/", summary="根路径版本信息")
async def root_version():
    """根路径返回版本信息"""
    return await get_version()

