import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import cast
from urllib.parse import urljoin, urlparse

from shared.core.exceptions.domain_exceptions import ValidationException

AddressInfo = tuple[int, int, int, str, tuple[str, ...]]
AllowedIPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
MAX_SAFE_REDIRECTS = 5


class URLSecurityError(ValueError):
    """Base error for URL safety validation failures."""


class HostnameResolutionError(URLSecurityError):
    """Raised when a hostname cannot be resolved."""


class HostnameNotAllowedError(URLSecurityError):
    """Raised when a hostname resolves to a blocked network address."""


class InvalidResolvedAddressError(URLSecurityError):
    """Raised when DNS returns an invalid IP address."""


class UnsupportedURLSchemeError(URLSecurityError):
    """Raised when a URL uses a disallowed scheme."""


class MissingURLHostnameError(URLSecurityError):
    """Raised when a URL does not include a hostname."""


class SafePublicHTTPURL(str):
    """A URL string that has passed public HTTP SSRF validation."""


@dataclass(frozen=True)
class PublicHTTPURLValidationResult:
    """Validated public HTTP URL and its pinned public IP address."""

    url: SafePublicHTTPURL
    validated_ip: str


def validate_public_http_url(url: str, field: str = "url") -> None:
    """Reject URL inputs that could target internal networks or local services."""
    try:
        _validate_public_http_url(url)
    except UnsupportedURLSchemeError as exc:
        raise _build_url_validation_error(field, "URL must use http or https") from exc
    except MissingURLHostnameError as exc:
        raise _build_url_validation_error(field, "URL must include a hostname") from exc
    except HostnameResolutionError as exc:
        raise _build_url_validation_error(field, "URL hostname could not be resolved") from exc
    except InvalidResolvedAddressError as exc:
        raise _build_url_validation_error(field, "URL resolved to an invalid IP") from exc
    except HostnameNotAllowedError as exc:
        raise _build_url_validation_error(field, "URL host is not allowed") from exc


def validate_public_http_redirect_url(
    url: str,
    redirect_url: str,
    field: str = "url",
) -> SafePublicHTTPURL:
    """Resolve and validate an HTTP redirect target before following it."""
    resolved_url = urljoin(url, redirect_url)
    validate_public_http_url(resolved_url, field=field)
    return SafePublicHTTPURL(resolved_url)


def get_safe_public_http_url(url: str, field: str = "url") -> SafePublicHTTPURL:
    """Return a validated public HTTP URL for outbound HTTP clients."""
    validate_public_http_url(url, field=field)
    return SafePublicHTTPURL(url)


def validate_public_http_url_and_resolve_ip(
    url: str,
    field: str = "url",
) -> PublicHTTPURLValidationResult:
    """Validate a public HTTP URL and return the IP selected during validation."""
    try:
        validated_ip = _validate_public_http_url(url)
        return PublicHTTPURLValidationResult(
            url=SafePublicHTTPURL(url),
            validated_ip=validated_ip,
        )
    except UnsupportedURLSchemeError as exc:
        raise _build_url_validation_error(field, "URL must use http or https") from exc
    except MissingURLHostnameError as exc:
        raise _build_url_validation_error(field, "URL must include a hostname") from exc
    except HostnameResolutionError as exc:
        raise _build_url_validation_error(field, "URL hostname could not be resolved") from exc
    except InvalidResolvedAddressError as exc:
        raise _build_url_validation_error(field, "URL resolved to an invalid IP") from exc
    except HostnameNotAllowedError as exc:
        raise _build_url_validation_error(field, "URL host is not allowed") from exc


async def validate_public_http_url_and_resolve_ip_async(
    url: str,
    field: str = "url",
) -> PublicHTTPURLValidationResult:
    """Validate a public HTTP URL asynchronously and return the selected IP."""
    try:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"}:
            raise UnsupportedURLSchemeError(
                f"Unsupported URL scheme: {parsed_url.scheme}"
            )

        hostname = parsed_url.hostname
        if not hostname:
            raise MissingURLHostnameError("URL must include a hostname")

        validated_ip = await resolve_public_hostname_async(hostname)
        return PublicHTTPURLValidationResult(
            url=SafePublicHTTPURL(url),
            validated_ip=validated_ip,
        )
    except UnsupportedURLSchemeError as exc:
        raise _build_url_validation_error(field, "URL must use http or https") from exc
    except MissingURLHostnameError as exc:
        raise _build_url_validation_error(field, "URL must include a hostname") from exc
    except HostnameResolutionError as exc:
        raise _build_url_validation_error(field, "URL hostname could not be resolved") from exc
    except InvalidResolvedAddressError as exc:
        raise _build_url_validation_error(field, "URL resolved to an invalid IP") from exc
    except HostnameNotAllowedError as exc:
        raise _build_url_validation_error(field, "URL host is not allowed") from exc


def get_safe_redirect_url(url: str, redirect_url: str) -> str:
    """Resolve and validate an HTTP redirect target for internal network callers."""
    resolved_url = urljoin(url, redirect_url)
    _validate_public_http_url(resolved_url)
    return resolved_url


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


def _validate_public_http_url(url: str) -> str:
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"}:
        raise UnsupportedURLSchemeError(f"Unsupported URL scheme: {parsed_url.scheme}")

    hostname = parsed_url.hostname
    if not hostname:
        raise MissingURLHostnameError("URL must include a hostname")

    return resolve_public_hostname(hostname)


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
