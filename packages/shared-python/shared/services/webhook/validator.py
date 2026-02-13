"""
Webhook Validation Utilities

Provides validation logic for webhook URLs with comprehensive SSRF protection.

Protection layers (inspired by gradio-app/safehttpx + OWASP SSRF Prevention):
1. Scheme enforcement (HTTPS only in production)
2. Hostname normalization and suspicious pattern detection
3. DNS resolution via getaddrinfo (IPv4 + IPv6)
4. IP classification (blocks private/loopback/link-local/multicast/reserved)
5. Cloud metadata endpoint blocking (AWS, GCP, Azure)
6. IP obfuscation detection (decimal, octal, hex, IPv6-mapped IPv4)
7. Google DNS fallback for secondary validation
8. Returns validated IP for connection pinning (anti-DNS-rebinding)
9. Domain whitelist support for trusted endpoints
"""
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from loguru import logger

from shared.core.config import app_config


# Cloud metadata endpoints that must always be blocked regardless of IP checks
CLOUD_METADATA_HOSTNAMES: set[str] = {
    "metadata.google.internal",
    "metadata.goog",
    "169.254.169.254",
    "fd00:ec2::254",
}

# Regex patterns for IP obfuscation in hostnames
# Matches decimal (e.g. 2130706433), octal (e.g. 0177.0.0.1), hex (e.g. 0x7f000001)
DECIMAL_IP_PATTERN: re.Pattern[str] = re.compile(r"^\d{8,10}$")
OCTAL_IP_PATTERN: re.Pattern[str] = re.compile(r"^0[0-7]+(\.[0-7]+){0,3}$")
HEX_IP_PATTERN: re.Pattern[str] = re.compile(r"^0x[0-9a-fA-F]+$")

GOOGLE_DNS_TIMEOUT_SECONDS: float = 3.0


@dataclass
class WebhookValidationResult:
    """Result of webhook URL validation, including pinned IP for anti-DNS-rebinding."""
    is_valid: bool
    error_message: Optional[str] = None
    validated_ip: Optional[str] = None  # Pinned IP to use for connection
    hostname: Optional[str] = None      # Original hostname for Host header / SNI


def is_public_ip(ip_address_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address is public (not private/loopback/link-local/multicast/reserved)."""
    return not (
        ip_address_obj.is_private
        or ip_address_obj.is_loopback
        or ip_address_obj.is_link_local
        or ip_address_obj.is_multicast
        or ip_address_obj.is_reserved
        or ip_address_obj.is_unspecified
    )


def is_cloud_metadata_ip(ip_address_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Explicitly block known cloud metadata service IPs."""
    metadata_ips: set[str] = {
        "169.254.169.254",       # AWS / GCP / most clouds
        "fd00:ec2::254",         # AWS IPv6 metadata
        "169.254.170.2",         # AWS ECS task metadata
        "100.100.100.200",       # Alibaba Cloud metadata
    }
    return str(ip_address_obj) in metadata_ips


def detect_ip_obfuscation(hostname: str) -> Tuple[bool, Optional[str]]:
    """
    Detect IP address obfuscation techniques used to bypass SSRF filters.

    Attackers encode IPs in non-standard formats that resolve to internal addresses:
    - Decimal: 2130706433 → 127.0.0.1
    - Octal: 0177.0.0.1 → 127.0.0.1
    - Hex: 0x7f000001 → 127.0.0.1
    - IPv6-mapped IPv4: ::ffff:127.0.0.1 → 127.0.0.1

    Returns:
        Tuple of (is_obfuscated, description)
    """
    lower_hostname: str = hostname.lower().strip()

    # Check decimal IP (e.g. 2130706433)
    if DECIMAL_IP_PATTERN.match(lower_hostname):
        return True, f"Decimal IP encoding detected: {hostname}"

    # Check octal IP (e.g. 0177.0.0.1)
    if OCTAL_IP_PATTERN.match(lower_hostname):
        return True, f"Octal IP encoding detected: {hostname}"

    # Check hex IP (e.g. 0x7f000001)
    if HEX_IP_PATTERN.match(lower_hostname):
        return True, f"Hex IP encoding detected: {hostname}"

    # Check IPv6-mapped IPv4 (e.g. ::ffff:127.0.0.1, ::ffff:7f00:1)
    if lower_hostname.startswith("::ffff:"):
        return True, f"IPv6-mapped IPv4 detected: {hostname}"

    # Check bracket-enclosed IPv6 with mapped IPv4
    if lower_hostname.startswith("[::ffff:"):
        return True, f"Bracketed IPv6-mapped IPv4 detected: {hostname}"

    return False, None


def resolve_all_ips(hostname: str) -> List[str]:
    """
    Resolve hostname to all IP addresses using getaddrinfo (IPv4 + IPv6).

    Unlike gethostbyname which only returns a single IPv4 address,
    getaddrinfo returns all addresses for both address families.
    An attacker could hide a private IPv6 address behind a public IPv4.

    Returns IPv4 addresses first (preferred for connection pinning compatibility).
    """
    ipv4_ips: list[str] = []
    ipv6_ips: list[str] = []
    seen: set[str] = set()
    try:
        addr_infos = socket.getaddrinfo(
            hostname, None,
            family=socket.AF_UNSPEC,  # Both IPv4 and IPv6
            type=socket.SOCK_STREAM
        )
        for family, _, _, _, sockaddr in addr_infos:
            ip_str: str = str(sockaddr[0])
            # Normalize IPv6 addresses (strip zone ID, scope)
            if family == socket.AF_INET6:
                ip_str = ip_str.split("%")[0]
            if ip_str not in seen:
                seen.add(ip_str)
                if family == socket.AF_INET:
                    ipv4_ips.append(ip_str)
                else:
                    ipv6_ips.append(ip_str)
    except socket.gaierror:
        pass
    # IPv4 first — better compatibility with PinnedResolver and most webhook endpoints
    return ipv4_ips + ipv6_ips


async def resolve_via_google_dns(hostname: str) -> List[str]:
    """
    Secondary DNS resolution via Google's public DNS-over-HTTPS.

    This provides a second opinion that's harder for an attacker to poison
    compared to the local system resolver. If Google DNS returns different
    IPs than the system resolver, it may indicate DNS poisoning or rebinding.
    """
    resolved_ips: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=GOOGLE_DNS_TIMEOUT_SECONDS) as client:
            # Query both A (IPv4) and AAAA (IPv6) records
            for record_type in ("A", "AAAA"):
                response = await client.get(
                    "https://dns.google/resolve",
                    params={"name": hostname, "type": record_type},
                )
                if response.status_code == 200:
                    data = response.json()
                    for answer in data.get("Answer", []):
                        ip_str: str = answer.get("data", "")
                        if ip_str:
                            resolved_ips.append(ip_str)
    except Exception as error:
        logger.warning(f"Google DNS fallback failed for {hostname}: {error}")
    return resolved_ips


def classify_ip(ip_str: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a single IP address against all SSRF rules.

    Returns:
        Tuple of (is_safe, error_message). is_safe=True means the IP is public.
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, f"Invalid IP address: {ip_str}"

    # Explicit cloud metadata check (defense-in-depth, catches even if is_link_local misses)
    if is_cloud_metadata_ip(ip_obj):
        return False, f"Cloud metadata endpoint blocked: {ip_str}"

    if ip_obj.is_loopback:
        return False, f"Loopback addresses are not allowed: {ip_str}"
    if ip_obj.is_private:
        return False, f"Private network addresses are not allowed: {ip_str}"
    if ip_obj.is_link_local:
        return False, f"Link-local addresses are not allowed: {ip_str}"
    if ip_obj.is_multicast:
        return False, f"Multicast addresses are not allowed: {ip_str}"
    if ip_obj.is_reserved:
        return False, f"Reserved addresses are not allowed: {ip_str}"
    if ip_obj.is_unspecified:
        return False, f"Unspecified addresses are not allowed: {ip_str}"

    # Check IPv6-mapped IPv4 — the mapped IPv4 part must also be public
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        mapped_v4 = ip_obj.ipv4_mapped
        if not is_public_ip(mapped_v4):
            return False, f"IPv6-mapped IPv4 resolves to non-public address: {mapped_v4}"

    return True, None


async def validate_webhook_url_async(
    url: str,
    allowed_domains: Optional[List[str]] = None,
) -> WebhookValidationResult:
    """
    Comprehensive async webhook URL validation with SSRF protection.

    Performs all validation layers and returns a pinned IP for the dispatcher
    to use, eliminating the DNS rebinding TOCTOU window.

    Args:
        url: Target URL to validate
        allowed_domains: Optional whitelist — if set, only these domains are allowed

    Returns:
        WebhookValidationResult with validated_ip for connection pinning
    """
    try:
        parsed = urlparse(url)

        # Layer 1: Scheme enforcement
        is_dev: bool = app_config.ENVIRONMENT.lower() in ("dev", "development", "local")
        allowed_schemes: list[str] = ["https"] if not is_dev else ["https", "http"]

        if parsed.scheme not in allowed_schemes:
            return WebhookValidationResult(
                is_valid=False,
                error_message=f"Invalid scheme: {parsed.scheme}. Must be HTTPS.",
            )

        # Layer 2: Hostname must exist
        hostname: Optional[str] = parsed.hostname
        if not hostname:
            return WebhookValidationResult(
                is_valid=False, error_message="URL must have a hostname"
            )

        # Layer 3: Domain whitelist (if configured)
        if allowed_domains:
            normalized_hostname: str = hostname.lower().rstrip(".")
            if normalized_hostname not in {d.lower().rstrip(".") for d in allowed_domains}:
                return WebhookValidationResult(
                    is_valid=False,
                    error_message=f"Domain not in whitelist: {hostname}",
                )

        # Layer 4: Cloud metadata hostname check
        if hostname.lower() in CLOUD_METADATA_HOSTNAMES:
            return WebhookValidationResult(
                is_valid=False,
                error_message=f"Cloud metadata endpoint blocked: {hostname}",
            )

        # Layer 5: IP obfuscation detection
        is_obfuscated, obfuscation_msg = detect_ip_obfuscation(hostname)
        if is_obfuscated:
            return WebhookValidationResult(
                is_valid=False, error_message=obfuscation_msg
            )

        # Layer 6: DNS resolution (system resolver, IPv4 + IPv6)
        system_ips: List[str] = resolve_all_ips(hostname)
        if not system_ips:
            return WebhookValidationResult(
                is_valid=False,
                error_message=f"DNS resolution failed: no addresses for {hostname}",
            )

        # Layer 7: Classify ALL resolved IPs — every one must be public
        for ip_str in system_ips:
            is_safe, error_msg = classify_ip(ip_str)
            if not is_safe:
                return WebhookValidationResult(
                    is_valid=False, error_message=error_msg
                )

        # Layer 8: Google DNS cross-validation (non-blocking, best-effort)
        google_ips: List[str] = await resolve_via_google_dns(hostname)
        if google_ips:
            for ip_str in google_ips:
                is_safe, error_msg = classify_ip(ip_str)
                if not is_safe:
                    return WebhookValidationResult(
                        is_valid=False,
                        error_message=f"Google DNS returned unsafe IP: {error_msg}",
                    )

        # Pick the first validated IP for connection pinning
        pinned_ip: str = system_ips[0]

        return WebhookValidationResult(
            is_valid=True,
            validated_ip=pinned_ip,
            hostname=hostname,
        )

    except Exception as error:
        return WebhookValidationResult(
            is_valid=False, error_message=f"URL validation failed: {error}"
        )


def validate_webhook_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Synchronous backward-compatible wrapper for webhook URL validation.

    Used by the jobs route for quick pre-flight validation at submission time.
    Does NOT return a pinned IP — the dispatcher should call
    validate_webhook_url_async for full protection including IP pinning.

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        parsed = urlparse(url)

        # Scheme check
        is_dev: bool = app_config.ENVIRONMENT.lower() in ("dev", "development", "local")
        allowed_schemes: list[str] = ["https"] if not is_dev else ["https", "http"]

        if parsed.scheme not in allowed_schemes:
            return False, f"Invalid scheme: {parsed.scheme}. Must be HTTPS."

        hostname: Optional[str] = parsed.hostname
        if not hostname:
            return False, "URL must have a hostname"

        # Cloud metadata hostname check
        if hostname.lower() in CLOUD_METADATA_HOSTNAMES:
            return False, f"Cloud metadata endpoint blocked: {hostname}"

        # IP obfuscation detection
        is_obfuscated, obfuscation_msg = detect_ip_obfuscation(hostname)
        if is_obfuscated:
            return False, obfuscation_msg

        # DNS resolution (IPv4 + IPv6)
        system_ips: List[str] = resolve_all_ips(hostname)
        if not system_ips:
            return False, f"DNS resolution failed: no addresses for {hostname}"

        # Classify all resolved IPs
        for ip_str in system_ips:
            is_safe, error_msg = classify_ip(ip_str)
            if not is_safe:
                return False, error_msg

        return True, None

    except Exception as error:
        return False, f"URL validation failed: {error}"
