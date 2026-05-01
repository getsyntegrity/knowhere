"""API key hashing helpers."""

import hmac
from hashlib import sha256


def hash_api_key(api_key: str) -> str:
    """Return a deterministic keyed digest for API key lookup."""
    from shared.core.config import settings

    secret_key = settings.SECRET_KEY.encode("utf-8")
    api_key_bytes = api_key.encode("utf-8")
    return hmac.new(secret_key, api_key_bytes, sha256).hexdigest()
