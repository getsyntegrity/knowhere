"""
API v1 route registry.
"""
from app.api.v1 import health
from app.api.v1.routes import (api_key, billing, guest, jobs, knowledge_base,
                               qstash_callbacks, s3_events, version,
                               webhook, webhook_secrets)
from fastapi import APIRouter

api_router = APIRouter()


# API Key management
api_router.include_router(api_key.router, prefix="/auth", tags=["API Key管理"])

# Guest registration (unauthenticated, IP-rate-limited)
api_router.include_router(guest.router, prefix="/guest", tags=["Guest Registration"])

# Billing
api_router.include_router(billing.router, prefix="/billing", tags=["计费管理"])

# Knowledge base
api_router.include_router(knowledge_base.router, prefix="/kb", tags=["知识库"])

# Unified Jobs routes
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])

# S3 event webhook (internal)
api_router.include_router(s3_events.router, prefix="/internal", tags=["Internal"])

api_router.include_router(webhook.router, prefix="/webhooks", tags=["Webhook管理"])

api_router.include_router(webhook_secrets.router, prefix="/webhooks/secrets", tags=["Webhook Secrets"])

# QStash delivery callbacks (no auth — verified by QStash JWT signature)
api_router.include_router(qstash_callbacks.router, prefix="/webhooks", tags=["QStash Callbacks"])

# Health check
api_router.include_router(health.router, prefix="/health", tags=["健康检查"])

# Version info
api_router.include_router(version.router, tags=["版本信息"])

__all__ = ["api_router"]
