"""
Upload expiry utility — shared by S3 webhook guard and worker sweeper.

Centralizes the age-check logic so both code paths use identical rules.
"""
from datetime import datetime, timezone


def is_upload_expired(created_at: datetime | None, max_age_seconds: int) -> bool:
    """Return True if a job has exceeded its upload window.

    Args:
        created_at: Job creation timestamp (tz-aware or naive-UTC).
        max_age_seconds: Maximum allowed age in seconds.
            If <= 0, expiry checking is disabled.

    Returns:
        True when the job should be considered expired.
    """
    if max_age_seconds <= 0 or created_at is None:
        return False

    created_utc = (
        created_at.replace(tzinfo=timezone.utc)
        if created_at.tzinfo is None
        else created_at
    )
    age = (datetime.now(timezone.utc) - created_utc).total_seconds()
    return age > max_age_seconds
