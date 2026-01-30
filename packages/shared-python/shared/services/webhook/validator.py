"""
Webhook Validation Utilities

Provides validation logic for webhook URLs, including SSRF protection.
"""
import os
import socket
import ipaddress
from urllib.parse import urlparse
from typing import Tuple, Optional


from shared.core.config import app_config

def validate_webhook_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate target URL for SSRF protection.
    
    Checks:
    1. Scheme must be https (or http in DEV mode)
    2. Hostname must resolve to public IP
    3. Reject private/loopback/link-local IPs
    
    Args:
        url: Target URL to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        parsed = urlparse(url)
        
        # 1. Scheme check
        is_dev = app_config.ENVIRONMENT.lower() in ('dev', 'development', 'local')
        allowed_schemes = ['https'] if not is_dev else ['https', 'http']
        
        if parsed.scheme not in allowed_schemes:
            return False, f"Invalid scheme: {parsed.scheme}. Must be HTTPS."
        
        # 2. Hostname must exist
        hostname = parsed.hostname
        if not hostname:
            return False, "URL must have a hostname"
        
        # 3. Resolve DNS and check IP
        try:
            ip_str = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(ip_str)
        except socket.gaierror as e:
            return False, f"DNS resolution failed: {e}"
        
        # 4. Block private/reserved IPs
        if ip.is_loopback:
            return False, f"Loopback addresses are not allowed: {ip_str}"
        if ip.is_private:
            return False, f"Private network addresses are not allowed: {ip_str}"
        if ip.is_link_local:
            return False, f"Link-local addresses are not allowed: {ip_str}"
        if ip.is_multicast:
            return False, f"Multicast addresses are not allowed: {ip_str}"
        if ip.is_reserved:
            return False, f"Reserved addresses are not allowed: {ip_str}"
        
        return True, None
        
    except Exception as e:
        return False, f"URL validation failed: {e}"
