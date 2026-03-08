"""
Webhook Validation Utilities

SSRF protection via DNS resolution + is_global check + IP pinning.
"""
import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from shared.core.config import app_config


# ── Core SSRF checks ─────────────────────


def is_public_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


async def async_validate_url(hostname: str) -> str:
    """Validate hostname resolves to a public IP. Returns pinned IP."""
    try:
        loop = asyncio.get_event_loop()
        addrinfo = await loop.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Unable to resolve hostname {hostname}: {exc}") from exc

    for family, _, _, _, sockaddr in addrinfo:
        ip_address = sockaddr[0]
        if family in (socket.AF_INET, socket.AF_INET6) and is_public_ip(ip_address):
            return ip_address

    raise ValueError(f"Hostname {hostname} failed validation")


def validate_url(hostname: str) -> str:
    """Sync hostname validation. Returns pinned public IP."""
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Unable to resolve hostname {hostname}: {exc}") from exc

    for family, _, _, _, sockaddr in addrinfo:
        ip_address = sockaddr[0]
        if family in (socket.AF_INET, socket.AF_INET6) and is_public_ip(ip_address):
            return ip_address

    raise ValueError(f"Hostname {hostname} failed validation")


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
            return WebhookValidationResult(is_valid=False, error_message=f"Invalid scheme: {parsed.scheme}. Must be HTTPS.")
        hostname: Optional[str] = parsed.hostname
        if not hostname:
            return WebhookValidationResult(is_valid=False, error_message="URL must have a hostname")
        validated_ip: str = await async_validate_url(hostname)
        return WebhookValidationResult(
            is_valid=True, validated_ip=validated_ip, hostname=hostname,
        )
    except ValueError as exc:
        return WebhookValidationResult(is_valid=False, error_message=str(exc))
    except Exception as exc:
        return WebhookValidationResult(
            is_valid=False, error_message=f"URL validation failed: {exc}",
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
            return WebhookValidationResult(is_valid=False, error_message="URL must have a hostname")

        validated_ip: str = validate_url(hostname)
        return WebhookValidationResult(
            is_valid=True,
            validated_ip=validated_ip,
            hostname=hostname,
        )
    except ValueError as exc:
        return WebhookValidationResult(is_valid=False, error_message=str(exc))
    except Exception as exc:
        return WebhookValidationResult(
            is_valid=False, error_message=f"URL validation failed: {exc}",
        )
