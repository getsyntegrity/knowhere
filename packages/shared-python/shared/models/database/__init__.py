"""
Database Models Package
Ensure all models are correctly imported to avoid circular import issues
"""

# 2. Then import models that depend on User
from .api_key import APIKey
from .credits_transaction import CreditsTransaction
from .email_log import EmailLog
from .job import Job
from .job_result import JobChunk, JobResult
from .subscription import Subscription
from .usage_log import UsageLog
from .user_balance import UserBalance  # Added
from .stripe_price_config import StripePriceConfig
from .payment_record import PaymentRecord

# Import models in dependency order
# 1. First import base models (no foreign key dependencies)
# from .user import Role, User, UserType

# 3. Job-related log models
from .job_state_audit_log import JobStateAuditLog
from .job_state_history import JobStateHistory
from .webhook_log import WebhookLog
from .webhook import WebhookEvent, WebhookEventStatus
from .webhook_secret import WebhookSecret, WebhookSecretStatus

# 4. Finally import other models
# from .oauth_provider import OAuthProvider  # Commented out temporarily to avoid circular imports

__all__ = [
    # "User", 
    # "Role", 
    # "UserType",
    "APIKey",
    "Subscription",
    "CreditsTransaction",
    "UsageLog",
    "UserBalance",  # Added
    "EmailLog",
    "Job",
    "JobResult",
    "JobChunk",
    "StripePriceConfig",
    "PaymentRecord",
    "JobStateAuditLog",
    "JobStateHistory",
    "WebhookLog",
    "WebhookEvent",
    "WebhookEventStatus",
    "WebhookSecret",
    "WebhookSecretStatus"
    # "OAuthProvider"
]
