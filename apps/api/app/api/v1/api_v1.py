"""
API v1 route registry.
"""

from app.api.v1 import health
from app.api.v1.routes import (
    api_key,
    documents,
    guest,
    jobs,
    knowledge_base,
    qstash_callbacks,
    retrieval,
    s3_events,
    version,
    webhook,
    webhook_secrets,
)
from fastapi import APIRouter

from shared.core.config import settings

api_router = APIRouter()


# API Key management
api_router.include_router(api_key.router, prefix="/auth", tags=["API Key Management"])

# Guest registration
api_router.include_router(guest.router, prefix="/guest", tags=["Guest Registration"])

# Billing
if settings.BILLING_ENABLED:
    from app.api.v1.routes import billing

    api_router.include_router(billing.router, prefix="/billing", tags=["Billing"])

# Knowledge base
api_router.include_router(knowledge_base.router, prefix="/kb", tags=["Knowledge Base"])

# Unified Jobs routes
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])

# Retrieval
api_router.include_router(retrieval.router, prefix="/retrieval", tags=["Retrieval"])

# Documents
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])

# S3 event webhook (internal)
api_router.include_router(s3_events.router, prefix="/internal", tags=["Internal"])

api_router.include_router(
    webhook.router, prefix="/webhooks", tags=["Webhook Management"]
)

api_router.include_router(
    webhook_secrets.router, prefix="/webhooks/secrets", tags=["Webhook Secrets"]
)

# QStash delivery callbacks (no auth — verified by QStash JWT signature)
api_router.include_router(
    qstash_callbacks.router, prefix="/webhooks", tags=["QStash Callbacks"]
)

# Health check
api_router.include_router(health.router, prefix="/health", tags=["Health"])

# Version info
api_router.include_router(version.router, tags=["Version"])

__all__ = ["api_router"]
