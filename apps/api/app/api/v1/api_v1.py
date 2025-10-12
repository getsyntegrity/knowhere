"""
API v1 路由总入口
"""
from fastapi import APIRouter
from app.api.v1.routes import auth, knowledge_base, oauth, api_key, billing, user_management, table_fill, kb_jobs, webhook, job_management

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

# 注册知识库路由
api_router.include_router(knowledge_base.router, prefix="/kb", tags=["知识库"])

# 注册队列管理路由
# 队列管理API已移除，使用Job API替代

# Redis演示路由已移除

# 注册表格填充路由
api_router.include_router(table_fill.router, prefix="/table-fill", tags=["表格填充"])

# 注册知识库任务路由
api_router.include_router(kb_jobs.router, prefix="/kb", tags=["知识库任务"])

# 注册Webhook管理路由
api_router.include_router(webhook.router, prefix="/webhooks", tags=["Webhook管理"])

# 注册Job管理路由
api_router.include_router(job_management.router, prefix="/jobs", tags=["Job管理"])

__all__ = ["api_router"]
