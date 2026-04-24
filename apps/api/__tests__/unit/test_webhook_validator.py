"""
Tests for webhook URL validator with SSRF protection (adapted from safehttpx).

Covers: scheme enforcement, IP classification,
async validation with IP pinning, and DNS failure.
"""

import pytest
from unittest.mock import patch, AsyncMock
from shared.services.webhook.validator import (
    validate_webhook_url_async,
    is_public_ip,
    async_validate_url,
)


# ── Scheme enforcement ──────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,expected_valid,error_fragment",
    [
        ("https://example.com/webhook", True, None),
        ("http://example.com/webhook", False, "Must be HTTPS"),
        ("ftp://example.com", False, "Invalid scheme"),
        ("https://", False, "URL must have a hostname"),
    ],
)
async def test_validation_scheme_basic(url, expected_valid, error_fragment):
    with (
        patch("shared.services.webhook.validator.app_config") as mock_config,
        patch(
            "shared.services.webhook.validator.async_validate_url",
            new_callable=AsyncMock,
            return_value="93.184.216.34",
        ),
    ):
        mock_config.ENVIRONMENT = "production"
        result = await validate_webhook_url_async(url)
        assert result.is_valid == expected_valid
        if error_fragment:
            assert result.error_message and error_fragment in result.error_message


@pytest.mark.asyncio
async def test_validation_dev_mode():
    with (
        patch("shared.services.webhook.validator.app_config") as mock_config,
        patch(
            "shared.services.webhook.validator.async_validate_url",
            new_callable=AsyncMock,
            return_value="93.184.216.34",
        ),
    ):
        mock_config.ENVIRONMENT = "development"
        result = await validate_webhook_url_async("http://example.com/webhook")
    assert result.is_valid is True


# ── IP classification ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ip_str,expected_public",
    [
        ("93.184.216.34", True),  # Public IPv4
        ("8.8.8.8", True),  # Google DNS
        ("127.0.0.1", False),  # Loopback
        ("10.0.0.1", False),  # Private (RFC 1918)
        ("172.16.0.1", False),  # Private (RFC 1918)
        ("192.168.1.1", False),  # Private (RFC 1918)
        ("169.254.169.254", False),  # Link-local / AWS metadata
        ("0.0.0.0", False),  # Unspecified
        ("::1", False),  # IPv6 loopback
        ("fe80::1", False),  # IPv6 link-local
        ("fd00::1", False),  # IPv6 ULA (private)
        ("100.64.0.1", False),  # Carrier-Grade NAT
        ("100.127.255.254", False),  # CGNAT upper bound
    ],
)
def test_is_public_ip(ip_str, expected_public):
    assert is_public_ip(ip_str) == expected_public


# ── Cloud metadata IPs blocked via is_public_ip ──────────────────────


@pytest.mark.parametrize(
    "ip_str",
    [
        "169.254.169.254",  # AWS/GCP metadata (link-local)
        "fd00:ec2::254",  # AWS IPv6 metadata (private)
        "169.254.170.2",  # AWS ECS task metadata (link-local)
        "100.100.100.200",  # Alibaba Cloud metadata (CGNAT)
    ],
)
def test_cloud_metadata_ips_blocked(ip_str):
    assert is_public_ip(ip_str) is False


# ── Async validation with IP pinning ─────────────────────────────────


@pytest.mark.asyncio
async def test_async_validation_returns_pinned_ip():
    with (
        patch("shared.services.webhook.validator.app_config") as mock_config,
        patch(
            "shared.services.webhook.validator.async_validate_url",
            new_callable=AsyncMock,
            return_value="93.184.216.34",
        ),
    ):
        mock_config.ENVIRONMENT = "production"
        result = await validate_webhook_url_async("https://example.com/webhook")
    assert result.is_valid is True
    assert result.validated_ip == "93.184.216.34"
    assert result.hostname == "example.com"


@pytest.mark.asyncio
async def test_async_validation_blocks_private_ip():
    with (
        patch("shared.services.webhook.validator.app_config") as mock_config,
        patch(
            "shared.services.webhook.validator.async_validate_url",
            new_callable=AsyncMock,
            side_effect=ValueError("Hostname evil.com failed validation"),
        ),
    ):
        mock_config.ENVIRONMENT = "production"
        result = await validate_webhook_url_async("https://evil.com/webhook")
    assert result.is_valid is False
    assert "failed validation" in result.error_message


@pytest.mark.asyncio
async def test_async_validation_dns_failure():
    with (
        patch("shared.services.webhook.validator.app_config") as mock_config,
        patch(
            "shared.services.webhook.validator.async_validate_url",
            new_callable=AsyncMock,
            side_effect=ValueError("Unable to resolve hostname nonexistent.invalid"),
        ),
    ):
        mock_config.ENVIRONMENT = "production"
        result = await validate_webhook_url_async("https://nonexistent.invalid/webhook")
    assert result.is_valid is False
    assert "Unable to resolve" in result.error_message


# ── async_validate_url (safehttpx core) ──────────────────────────────


@pytest.mark.asyncio
async def test_async_validate_url_returns_first_public_ip():
    import socket

    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
    ]
    with patch("asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.getaddrinfo = AsyncMock(return_value=mock_addrinfo)
        ip = await async_validate_url("example.com")
    assert ip == "93.184.216.34"


@pytest.mark.asyncio
async def test_async_validate_url_rejects_all_private():
    import socket

    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0)),
    ]
    with patch("asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.getaddrinfo = AsyncMock(return_value=mock_addrinfo)
        with pytest.raises(ValueError, match="failed validation"):
            await async_validate_url("evil.com")
