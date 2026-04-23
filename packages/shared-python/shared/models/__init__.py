"""Model registry used to avoid circular imports."""
from shared.models.database.api_key import APIKey
from shared.models.database.credits_transaction import CreditsTransaction
from shared.models.database.job import Job
from shared.models.database.job_state_history import JobStateHistory
from shared.models.database.webhook_log import WebhookLog

# Ensure all shared models are registered.
__all__ = [
    "APIKey",
    "Job",
    "CreditsTransaction",
    "JobStateHistory",
    "WebhookLog",
    "OAuthProvider",
]
