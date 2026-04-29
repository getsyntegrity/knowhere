"""
Webhook Validation Utilities

SSRF protection via shared DNS/IP validation + IP pinning.
"""

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from shared.core.config import app_config
from shared.utils.url_security import resolve_public_hostname, resolve_public_hostname_async


# ── Integration wrapper for our dispatcher ────────────────────────────


@dataclass
class WebhookValidationResult:
    """Result of webhook URL validation, including pinned IP for anti-DNS-rebinding."""

    is_valid: bool
    error_message: Optional[str] = None
    validated_ip: Optional[str] = None
    hostname: Optional[str] = None


async def validate_webhook_url_async(url: str) -> WebhookValidationResult:
    """
    Async webhook URL validation with SSRF protection and IP pinning.

    Returns WebhookValidationResult with validated_ip for the dispatcher
    to pin the connection to, eliminating the DNS rebinding TOCTOU window.
    """
    try:
        parsed = urlparse(url)
        is_dev: bool = app_config.ENVIRONMENT.lower() in ("dev", "development", "local")
        allowed_schemes: list[str] = ["https"] if not is_dev else ["https", "http"]
        if parsed.scheme not in allowed_schemes:
            return WebhookValidationResult(
                is_valid=False,
                error_message=f"Invalid scheme: {parsed.scheme}. Must be HTTPS.",
            )
        hostname: Optional[str] = parsed.hostname
        if not hostname:
            return WebhookValidationResult(
                is_valid=False, error_message="URL must have a hostname"
            )
        validated_ip: str = await resolve_public_hostname_async(hostname)
        return WebhookValidationResult(
            is_valid=True,
            validated_ip=validated_ip,
            hostname=hostname,
        )
    except ValueError as exc:
        return WebhookValidationResult(is_valid=False, error_message=str(exc))
    except Exception as exc:
        return WebhookValidationResult(
            is_valid=False,
            error_message=f"URL validation failed: {exc}",
        )


def validate_webhook_url(url: str) -> WebhookValidationResult:
    """Sync webhook URL validation with SSRF checks."""
    try:
        parsed = urlparse(url)
        is_dev: bool = app_config.ENVIRONMENT.lower() in ("dev", "development", "local")
        allowed_schemes: list[str] = ["https"] if not is_dev else ["https", "http"]
        if parsed.scheme not in allowed_schemes:
            return WebhookValidationResult(
                is_valid=False,
                error_message=f"Invalid scheme: {parsed.scheme}. Must be HTTPS.",
            )

        hostname: Optional[str] = parsed.hostname
        if not hostname:
            return WebhookValidationResult(
                is_valid=False, error_message="URL must have a hostname"
            )

        validated_ip: str = resolve_public_hostname(hostname)
        return WebhookValidationResult(
            is_valid=True,
            validated_ip=validated_ip,
            hostname=hostname,
        )
    except ValueError as exc:
        return WebhookValidationResult(is_valid=False, error_message=str(exc))
    except Exception as exc:
        return WebhookValidationResult(
            is_valid=False,
            error_message=f"URL validation failed: {exc}",
        )
