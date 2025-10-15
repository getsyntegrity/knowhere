"""
API v1 路由总入口
"""
from fastapi import APIRouter
from app.api.v1.routes import auth, knowledge_base, oauth, api_key, billing, user_management, webhook, jobs, s3_events

api_router = APIRouter()

# 注册认证路由
api_router.include_router(auth.router, tags=["认证"])

# 注册OAuth认证路由
api_router.include_router(oauth.router, prefix="/auth", tags=["OAuth认证"])

# 注册API Key管理路由
api_router.include_router(api_key.router, prefix="/auth", tags=["API Key管理"])

# 注册计费路由
api_router.include_router(billing.router, prefix="/billing", tags=["计费管理"])

# 注册用户管理路由
api_router.include_router(user_management.router, prefix="/user", tags=["用户管理"])

# 注册知识库路由（保留目录管理功能）
api_router.include_router(knowledge_base.router, prefix="/kb", tags=["知识库"])

# 注册统一Jobs路由（符合PRD规范）
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])

# 注册S3事件Webhook路由（内部使用）
api_router.include_router(s3_events.router, prefix="/internal", tags=["Internal"])

# 注册队列管理路由
# 队列管理API已移除，使用Job API替代

# Redis演示路由已移除

# 旧接口已删除，统一使用 /v1/jobs 接口

# 注册Webhook管理路由
api_router.include_router(webhook.router, prefix="/webhooks", tags=["Webhook管理"])

# Job管理路由已合并到统一Jobs路由中，避免冲突

__all__ = ["api_router"]
