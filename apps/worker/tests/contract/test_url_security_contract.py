import socket

import pytest

from shared.core.exceptions.domain_exceptions import ValidationException
from shared.utils.url_security import validate_public_http_url


def test_rejects_localhost_url_without_dns_lookup() -> None:
    with pytest.raises(ValidationException):
        validate_public_http_url("http://localhost/internal", field="source_url")


def test_rejects_private_ip_address() -> None:
    with pytest.raises(ValidationException):
        validate_public_http_url("https://10.0.0.1/private.pdf", field="source_url")


def test_rejects_hostname_that_resolves_to_private_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve_private_address(
        host: str,
        port: int | None,
    ) -> list[tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve_private_address)

    with pytest.raises(ValidationException):
        validate_public_http_url("https://files.example.test/document.pdf")


def test_allows_hostname_that_resolves_to_public_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve_public_address(
        host: str,
        port: int | None,
    ) -> list[tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve_public_address)

    validate_public_http_url("https://files.example.test/document.pdf")
