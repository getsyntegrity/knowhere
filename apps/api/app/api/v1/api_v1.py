"""
API v1 路由总入口
"""
from app.api.v1 import health
from app.api.v1.routes import (api_key, billing, jobs, knowledge_base,
                               s3_events, version, webhook, webhook_secrets)
from fastapi import APIRouter

api_router = APIRouter()


# 注册API Key管理路由
api_router.include_router(api_key.router, prefix="/auth", tags=["API Key管理"])

# 注册计费路由
api_router.include_router(billing.router, prefix="/billing", tags=["计费管理"])

# 注册知识库路由（保留目录管理功能）
api_router.include_router(knowledge_base.router, prefix="/kb", tags=["知识库"])

# 注册统一Jobs路由（符合PRD规范）
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])

# 注册S3事件Webhook路由（内部使用）
api_router.include_router(s3_events.router, prefix="/internal", tags=["Internal"])

api_router.include_router(webhook.router, prefix="/webhooks", tags=["Webhook管理"])

api_router.include_router(webhook_secrets.router, prefix="/webhooks/secrets", tags=["Webhook Secrets"])

# 注册健康检查路由
api_router.include_router(health.router, prefix="/health", tags=["健康检查"])

# 注册版本信息路由
api_router.include_router(version.router, tags=["版本信息"])

# Job管理路由已合并到统一Jobs路由中，避免冲突

__all__ = ["api_router"]
