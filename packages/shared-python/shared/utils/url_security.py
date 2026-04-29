import ipaddress
import socket
from urllib.parse import urlparse

from shared.core.exceptions.domain_exceptions import ValidationException


def validate_public_http_url(url: str, field: str = "url") -> None:
    """Reject URL inputs that could target internal networks or local services."""
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"}:
        raise _build_url_validation_error(field, "URL must use http or https")

    hostname = parsed_url.hostname
    if not hostname:
        raise _build_url_validation_error(field, "URL must include a hostname")

    if _is_blocked_hostname(hostname):
        raise _build_url_validation_error(field, "URL host is not allowed")

    try:
        address_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise _build_url_validation_error(field, "URL hostname could not be resolved") from exc

    resolved_addresses = {
        address_info[4][0]
        for address_info in address_infos
        if address_info[4] and address_info[4][0]
    }
    if not resolved_addresses:
        raise _build_url_validation_error(field, "URL hostname could not be resolved")

    for address in resolved_addresses:
        try:
            ip_address = ipaddress.ip_address(address)
        except ValueError as exc:
            raise _build_url_validation_error(field, "URL resolved to an invalid IP") from exc
        if _is_blocked_ip_address(ip_address):
            raise _build_url_validation_error(field, "URL host is not allowed")


def _is_blocked_hostname(hostname: str) -> bool:
    normalized_hostname = hostname.rstrip(".").lower()
    if normalized_hostname in {"localhost", "ip6-localhost", "ip6-loopback"}:
        return True
    if normalized_hostname.endswith(".localhost") or normalized_hostname.endswith(".local"):
        return True
    return False


def _is_blocked_ip_address(ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip_address.is_private
        or ip_address.is_loopback
        or ip_address.is_link_local
        or ip_address.is_multicast
        or ip_address.is_reserved
        or ip_address.is_unspecified
    )


def _build_url_validation_error(field: str, description: str) -> ValidationException:
    return ValidationException(
        user_message="Invalid URL",
        violations=[{"field": field, "description": description}],
    )
