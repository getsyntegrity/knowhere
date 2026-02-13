"""
Tests for webhook URL validator with comprehensive SSRF protection.

Covers: scheme enforcement, IP classification, cloud metadata blocking,
IP obfuscation detection, DNS resolution, Google DNS fallback,
async validation with IP pinning, and domain whitelist.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from shared.services.webhook.validator import (
    validate_webhook_url,
    validate_webhook_url_async,
    detect_ip_obfuscation,
    classify_ip,
    is_cloud_metadata_ip,
    resolve_all_ips,
    WebhookValidationResult,
)


# ── Scheme enforcement ──────────────────────────────────────────────

@pytest.mark.parametrize("url,expected_valid,error_fragment", [
    ("https://example.com/webhook", True, None),
    ("http://example.com/webhook", False, "Must be HTTPS"),
    ("ftp://example.com", False, "Invalid scheme"),
    ("https://", False, "URL must have a hostname"),
])
def test_validation_scheme_basic(url, expected_valid, error_fragment):
    with patch("shared.services.webhook.validator.app_config") as mock_config:
        mock_config.ENVIRONMENT = "production"
        is_valid, error = validate_webhook_url(url)
        assert is_valid == expected_valid
        if error_fragment:
            assert error and error_fragment in error


@patch("shared.services.webhook.validator.app_config")
def test_validation_dev_mode(mock_config):
    mock_config.ENVIRONMENT = "development"
    with patch("shared.services.webhook.validator.resolve_all_ips", return_value=["93.184.216.34"]):
        is_valid, error = validate_webhook_url("http://example.com/webhook")
    assert is_valid is True
    assert error is None


# ── IP classification ────────────────────────────────────────────────

@pytest.mark.parametrize("ip_str,expected_safe", [
    ("93.184.216.34", True),       # Public IPv4
    ("8.8.8.8", True),             # Google DNS
    ("127.0.0.1", False),          # Loopback
    ("10.0.0.1", False),           # Private (RFC 1918)
    ("172.16.0.1", False),         # Private (RFC 1918)
    ("192.168.1.1", False),        # Private (RFC 1918)
    ("169.254.169.254", False),    # Link-local / AWS metadata
    ("0.0.0.0", False),            # Unspecified
    ("::1", False),                # IPv6 loopback
    ("fe80::1", False),            # IPv6 link-local
    ("fd00::1", False),            # IPv6 ULA (private)
])
def test_classify_ip(ip_str, expected_safe):
    is_safe, error = classify_ip(ip_str)
    assert is_safe == expected_safe


# ── Cloud metadata blocking ──────────────────────────────────────────

@pytest.mark.parametrize("hostname", [
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.goog",
    "[fd00:ec2::254]",
])
def test_cloud_metadata_hostname_blocked(hostname):
    with patch("shared.services.webhook.validator.app_config") as mock_config:
        mock_config.ENVIRONMENT = "production"
        is_valid, error = validate_webhook_url(f"https://{hostname}/latest/meta-data")
    assert is_valid is False
    assert "metadata" in error.lower() or "blocked" in error.lower()


@pytest.mark.parametrize("ip_str,expected_blocked", [
    ("169.254.169.254", True),     # AWS/GCP metadata
    ("fd00:ec2::254", True),       # AWS IPv6 metadata
    ("169.254.170.2", True),       # AWS ECS task metadata
    ("100.100.100.200", True),     # Alibaba Cloud metadata
    ("8.8.8.8", False),            # Not metadata
])
def test_cloud_metadata_ip_detection(ip_str, expected_blocked):
    import ipaddress
    ip_obj = ipaddress.ip_address(ip_str)
    assert is_cloud_metadata_ip(ip_obj) == expected_blocked


# ── IP obfuscation detection ─────────────────────────────────────────

@pytest.mark.parametrize("hostname,expected_obfuscated", [
    ("2130706433", True),          # Decimal for 127.0.0.1
    ("0177.0.0.1", True),         # Octal for 127.0.0.1
    ("0x7f000001", True),         # Hex for 127.0.0.1
    ("::ffff:127.0.0.1", True),   # IPv6-mapped IPv4
    ("[::ffff:127.0.0.1]", True), # Bracketed IPv6-mapped IPv4
    ("example.com", False),        # Normal hostname
    ("93.184.216.34", False),      # Normal IP (not obfuscated)
])
def test_ip_obfuscation_detection(hostname, expected_obfuscated):
    is_obfuscated, msg = detect_ip_obfuscation(hostname)
    assert is_obfuscated == expected_obfuscated


# ── Async validation with IP pinning ─────────────────────────────────

@pytest.mark.asyncio
async def test_async_validation_returns_pinned_ip():
    """validate_webhook_url_async should return a validated IP for connection pinning."""
    with patch("shared.services.webhook.validator.app_config") as mock_config, \
         patch("shared.services.webhook.validator.resolve_all_ips", return_value=["93.184.216.34"]), \
         patch("shared.services.webhook.validator.resolve_via_google_dns", new_callable=AsyncMock, return_value=[]):
        mock_config.ENVIRONMENT = "production"
        result = await validate_webhook_url_async("https://example.com/webhook")
    assert result.is_valid is True
    assert result.validated_ip == "93.184.216.34"
    assert result.hostname == "example.com"


@pytest.mark.asyncio
async def test_async_validation_blocks_private_ip():
    """Async validator should reject URLs that resolve to private IPs."""
    with patch("shared.services.webhook.validator.app_config") as mock_config, \
         patch("shared.services.webhook.validator.resolve_all_ips", return_value=["10.0.0.1"]), \
         patch("shared.services.webhook.validator.resolve_via_google_dns", new_callable=AsyncMock, return_value=[]):
        mock_config.ENVIRONMENT = "production"
        result = await validate_webhook_url_async("https://evil.com/webhook")
    assert result.is_valid is False
    assert "Private" in result.error_message


@pytest.mark.asyncio
async def test_async_validation_google_dns_catches_rebinding():
    """If Google DNS returns a private IP (even if system DNS returned public), block it."""
    with patch("shared.services.webhook.validator.app_config") as mock_config, \
         patch("shared.services.webhook.validator.resolve_all_ips", return_value=["93.184.216.34"]), \
         patch("shared.services.webhook.validator.resolve_via_google_dns", new_callable=AsyncMock, return_value=["10.0.0.1"]):
        mock_config.ENVIRONMENT = "production"
        result = await validate_webhook_url_async("https://rebinding.example.com/webhook")
    assert result.is_valid is False
    assert "Google DNS" in result.error_message


@pytest.mark.asyncio
async def test_async_validation_domain_whitelist():
    """Domain whitelist should reject non-whitelisted domains."""
    with patch("shared.services.webhook.validator.app_config") as mock_config, \
         patch("shared.services.webhook.validator.resolve_all_ips", return_value=["93.184.216.34"]), \
         patch("shared.services.webhook.validator.resolve_via_google_dns", new_callable=AsyncMock, return_value=[]):
        mock_config.ENVIRONMENT = "production"
        result = await validate_webhook_url_async(
            "https://evil.com/webhook",
            allowed_domains=["trusted.com", "api.trusted.com"],
        )
    assert result.is_valid is False
    assert "whitelist" in result.error_message.lower()


@pytest.mark.asyncio
async def test_async_validation_dns_failure():
    """Should reject URLs where DNS resolution returns no results."""
    with patch("shared.services.webhook.validator.app_config") as mock_config, \
         patch("shared.services.webhook.validator.resolve_all_ips", return_value=[]), \
         patch("shared.services.webhook.validator.resolve_via_google_dns", new_callable=AsyncMock, return_value=[]):
        mock_config.ENVIRONMENT = "production"
        result = await validate_webhook_url_async("https://nonexistent.invalid/webhook")
    assert result.is_valid is False
    assert "DNS resolution failed" in result.error_message


# ── SSRF blocking (sync wrapper) ─────────────────────────────────────

def test_sync_validation_blocks_loopback():
    with patch("shared.services.webhook.validator.app_config") as mock_config, \
         patch("shared.services.webhook.validator.resolve_all_ips", return_value=["127.0.0.1"]):
        mock_config.ENVIRONMENT = "production"
        is_valid, error = validate_webhook_url("https://localhost/webhook")
    assert is_valid is False
    assert "Loopback" in error


def test_sync_validation_blocks_private():
    with patch("shared.services.webhook.validator.app_config") as mock_config, \
         patch("shared.services.webhook.validator.resolve_all_ips", return_value=["192.168.1.1"]):
        mock_config.ENVIRONMENT = "production"
        is_valid, error = validate_webhook_url("https://internal.corp/webhook")
    assert is_valid is False
    assert "Private" in error


def test_sync_validation_allows_public():
    with patch("shared.services.webhook.validator.app_config") as mock_config, \
         patch("shared.services.webhook.validator.resolve_all_ips", return_value=["93.184.216.34"]):
        mock_config.ENVIRONMENT = "production"
        is_valid, error = validate_webhook_url("https://example.com/webhook")
    assert is_valid is True
    assert error is None
