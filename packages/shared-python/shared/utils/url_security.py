import asyncio
import ipaddress
import socket
from typing import cast
from urllib.parse import urlparse

from shared.core.exceptions.domain_exceptions import ValidationException

AddressInfo = tuple[int, int, int, str, tuple[str, ...]]
AllowedIPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class URLSecurityError(ValueError):
    """Base error for URL safety validation failures."""


class HostnameResolutionError(URLSecurityError):
    """Raised when a hostname cannot be resolved."""


class HostnameNotAllowedError(URLSecurityError):
    """Raised when a hostname resolves to a blocked network address."""


class InvalidResolvedAddressError(URLSecurityError):
    """Raised when DNS returns an invalid IP address."""


def validate_public_http_url(url: str, field: str = "url") -> None:
    """Reject URL inputs that could target internal networks or local services."""
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"}:
        raise _build_url_validation_error(field, "URL must use http or https")

    hostname = parsed_url.hostname
    if not hostname:
        raise _build_url_validation_error(field, "URL must include a hostname")

    try:
        resolve_public_hostname(hostname)
    except HostnameResolutionError as exc:
        raise _build_url_validation_error(field, "URL hostname could not be resolved") from exc
    except InvalidResolvedAddressError as exc:
        raise _build_url_validation_error(field, "URL resolved to an invalid IP") from exc
    except HostnameNotAllowedError as exc:
        raise _build_url_validation_error(field, "URL host is not allowed") from exc


def resolve_public_hostname(hostname: str) -> str:
    """Resolve a hostname to a public IP address and return the pinned IP."""
    _ensure_hostname_is_allowed(hostname)
    try:
        address_infos = cast(list[AddressInfo], socket.getaddrinfo(hostname, None))
    except socket.gaierror as exc:
        raise HostnameResolutionError(
            f"Unable to resolve hostname {hostname}: {exc}"
        ) from exc

    return _select_public_ip_address(hostname, address_infos)


async def resolve_public_hostname_async(hostname: str) -> str:
    """Resolve a hostname to a public IP address asynchronously."""
    _ensure_hostname_is_allowed(hostname)
    try:
        loop = asyncio.get_running_loop()
        address_infos = cast(
            list[AddressInfo],
            await loop.getaddrinfo(hostname, None),
        )
    except socket.gaierror as exc:
        raise HostnameResolutionError(
            f"Unable to resolve hostname {hostname}: {exc}"
        ) from exc

    return _select_public_ip_address(hostname, address_infos)


def is_public_ip_address(address: str) -> bool:
    """Return whether an IP string is safe to use as a public network target."""
    try:
        ip_address = ipaddress.ip_address(address)
    except ValueError:
        return False
    return _is_public_ip_address(ip_address)


def _ensure_hostname_is_allowed(hostname: str) -> None:
    if _is_blocked_hostname(hostname):
        raise HostnameNotAllowedError(f"Hostname {hostname} failed validation")


def _select_public_ip_address(hostname: str, address_infos: list[AddressInfo]) -> str:
    resolved_addresses = _extract_resolved_addresses(address_infos)
    if not resolved_addresses:
        raise HostnameResolutionError(f"Unable to resolve hostname {hostname}")

    selected_address: str | None = None
    for address in resolved_addresses:
        try:
            ip_address = ipaddress.ip_address(address)
        except ValueError as exc:
            raise InvalidResolvedAddressError(
                f"Hostname {hostname} resolved to invalid IP {address}"
            ) from exc
        if not _is_public_ip_address(ip_address):
            raise HostnameNotAllowedError(f"Hostname {hostname} failed validation")
        if selected_address is None:
            selected_address = address

    if selected_address:
        return selected_address
    raise HostnameNotAllowedError(f"Hostname {hostname} failed validation")


def _extract_resolved_addresses(address_infos: list[AddressInfo]) -> list[str]:
    resolved_addresses: list[str] = []
    seen_addresses: set[str] = set()
    for family, _, _, _, socket_address in address_infos:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        if not socket_address:
            continue
        address = socket_address[0]
        if address and address not in seen_addresses:
            resolved_addresses.append(address)
            seen_addresses.add(address)
    return resolved_addresses


def _is_blocked_hostname(hostname: str) -> bool:
    normalized_hostname = hostname.rstrip(".").lower()
    if normalized_hostname in {"localhost", "ip6-localhost", "ip6-loopback"}:
        return True
    if normalized_hostname.endswith(".localhost") or normalized_hostname.endswith(".local"):
        return True
    return False


def _is_public_ip_address(ip_address: AllowedIPAddress) -> bool:
    return ip_address.is_global and not _is_blocked_ip_address(ip_address)


def _is_blocked_ip_address(ip_address: AllowedIPAddress) -> bool:
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
