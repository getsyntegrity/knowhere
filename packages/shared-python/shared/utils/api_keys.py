"""API key generation, masking, and hashing helpers."""

import hmac
import os
from hashlib import sha256
from secrets import token_urlsafe
from typing import TypeGuard

API_KEY_PREFIX: str = "sk_"
API_KEY_RANDOM_BYTES: int = 32
API_KEY_HASH_SECRET_ENV: str = "API_KEY_HASH_SECRET"
APP_SECRET_ENV: str = "SECRET_KEY"


# TODO, use an alphanumeric api key
def generate_api_key() -> str:
    """Generate a new plaintext API key with cryptographic randomness."""
    return f"{API_KEY_PREFIX}{token_urlsafe(API_KEY_RANDOM_BYTES)}"


def hash_api_key(api_key: str) -> str:
    """Return a deterministic keyed digest for API key lookup."""
    return hmac.new(
        _get_api_key_hash_secret(),
        api_key.encode("utf-8"),
        sha256,
    ).hexdigest()


def _get_api_key_hash_secret() -> bytes:
    """Return the HMAC secret used to hash API keys for lookup."""
    secret = os.getenv(API_KEY_HASH_SECRET_ENV) or os.getenv(APP_SECRET_ENV)
    if not secret:
        raise RuntimeError(
            f"{API_KEY_HASH_SECRET_ENV} or {APP_SECRET_ENV} must be configured"
        )
    return secret.encode("utf-8")


def mask_api_key(api_key: str) -> str:
    """Mask an API key, exposing only the first 8 and last 4 characters."""
    if len(api_key) < 12:
        return api_key
    return api_key[:8] + "•" * (len(api_key) - 12) + api_key[-4:]


def is_api_key_token(token: object) -> TypeGuard[str]:
    """Return whether a bearer token has the API-key prefix."""
    return isinstance(token, str) and token.startswith(API_KEY_PREFIX)
