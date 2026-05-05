"""
Outbound URL Validation Utilities

Shared SSRF protection for outbound HTTP targets via DNS/IP validation + IP pinning.
"""

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from shared.core.config import app_config
from shared.utils.url_security import resolve_public_hostname, resolve_public_hostname_async


@dataclass
class OutboundURLValidationResult:
    """Result of outbound URL validation, including a pinned IP address."""

    is_valid: bool
    error_message: Optional[str] = None
    validated_ip: Optional[str] = None
    hostname: Optional[str] = None


async def validate_outbound_url_async(url: str) -> OutboundURLValidationResult:
    """
    Async outbound URL validation with SSRF protection and IP pinning.

    Returns OutboundURLValidationResult with a pinned IP address, eliminating
    the DNS rebinding TOCTOU window for later outbound requests.
    """
    try:
        parsed = urlparse(url)
        is_dev: bool = app_config.ENVIRONMENT.lower() in ("dev", "development", "local")
        allowed_schemes: list[str] = ["https"] if not is_dev else ["https", "http"]
        if parsed.scheme not in allowed_schemes:
            return OutboundURLValidationResult(
                is_valid=False,
                error_message=f"Invalid scheme: {parsed.scheme}. Must be HTTPS.",
            )
        hostname: Optional[str] = parsed.hostname
        if not hostname:
            return OutboundURLValidationResult(
                is_valid=False, error_message="URL must have a hostname"
            )
        validated_ip: str = await resolve_public_hostname_async(hostname)
        return OutboundURLValidationResult(
            is_valid=True,
            validated_ip=validated_ip,
            hostname=hostname,
        )
    except ValueError as exc:
        return OutboundURLValidationResult(is_valid=False, error_message=str(exc))
    except Exception as exc:
        return OutboundURLValidationResult(
            is_valid=False,
            error_message=f"URL validation failed: {exc}",
        )


def validate_outbound_url(url: str) -> OutboundURLValidationResult:
    """Sync outbound URL validation with SSRF checks."""
    try:
        parsed = urlparse(url)
        is_dev: bool = app_config.ENVIRONMENT.lower() in ("dev", "development", "local")
        allowed_schemes: list[str] = ["https"] if not is_dev else ["https", "http"]
        if parsed.scheme not in allowed_schemes:
            return OutboundURLValidationResult(
                is_valid=False,
                error_message=f"Invalid scheme: {parsed.scheme}. Must be HTTPS.",
            )

        hostname: Optional[str] = parsed.hostname
        if not hostname:
            return OutboundURLValidationResult(
                is_valid=False, error_message="URL must have a hostname"
            )

        validated_ip: str = resolve_public_hostname(hostname)
        return OutboundURLValidationResult(
            is_valid=True,
            validated_ip=validated_ip,
            hostname=hostname,
        )
    except ValueError as exc:
        return OutboundURLValidationResult(is_valid=False, error_message=str(exc))
    except Exception as exc:
        return OutboundURLValidationResult(
            is_valid=False,
            error_message=f"URL validation failed: {exc}",
        )
