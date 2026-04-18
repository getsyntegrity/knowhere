"""
Database Models Package
Ensure all models are correctly imported to avoid circular import issues
"""

# 2. Then import models that depend on User
from .api_key import APIKey
from .guest_device import GuestDevice
from .credits_transaction import CreditsTransaction
from .job import Job
from .job_result import JobChunk, JobResult
from .document import Document, DocumentChunk, DocumentSection

from .user_balance import UserBalance 
from .stripe_price_config import StripePriceConfig
from .payment_record import PaymentRecord

# Import models in dependency order
# 1. First import base models (no foreign key dependencies)
from .user import User

# 3. Job-related log models
from .job_state_audit_log import JobStateAuditLog
from .job_state_history import JobStateHistory
from .webhook_log import WebhookLog

# 4. Rate limit configuration models
from .tier_limit import TierLimit
from .system_limit import SystemLimit

# 5. Finally import other models
# from .oauth_provider import OAuthProvider  # Commented out temporarily to avoid circular imports

__all__ = [
    "User",
    "APIKey",
    "GuestDevice",
    "CreditsTransaction",

    "UserBalance",
    "Job",
    "JobResult",
    "JobChunk",
    "Document",
    "DocumentSection",
    "DocumentChunk",
    "StripePriceConfig",
    "PaymentRecord",
    "JobStateAuditLog",
    "JobStateHistory",
    "WebhookLog",
    "TierLimit",
    "SystemLimit",
    # "OAuthProvider"
]
