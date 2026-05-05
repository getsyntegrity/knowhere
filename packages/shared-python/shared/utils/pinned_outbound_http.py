"""
Pinned outbound HTTP helpers.

Shared infrastructure for outbound requests that must connect to a
pre-validated public IP address and block redirect-based SSRF.
"""

from __future__ import annotations

import socket
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import aiohttp
from aiohttp.abc import AbstractResolver

from shared.utils.url_security import SafePublicHTTPURL


@dataclass(frozen=True)
class PinnedOutboundResponse:
    """Minimal response metadata for pinned outbound HTTP requests."""

    status: int


class PinnedIPResolver(AbstractResolver):
    """Resolver that always returns the supplied pinned IP address."""

    def __init__(self, pinned_ip: str) -> None:
        self.pinned_ip = pinned_ip

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: int = socket.AF_INET,
    ) -> list[dict[str, Any]]:
        pinned_family: int = (
            socket.AF_INET6 if ":" in self.pinned_ip else socket.AF_INET
        )
        return [
            {
                "hostname": host,
                "host": self.pinned_ip,
                "port": port,
                "family": pinned_family,
                "proto": 0,
                "flags": socket.AI_NUMERICHOST,
            }
        ]

    async def close(self) -> None:
        pass


async def send_pinned_outbound_request(
    *,
    method: str,
    url: str,
    pinned_ip: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None = None,
    json_body: Any | None = None,
) -> PinnedOutboundResponse:
    """
    Send an outbound HTTP request through a resolver pinned to a validated IP.

    Redirects are always blocked to prevent redirect-based SSRF.
    """
    validated_url = SafePublicHTTPURL(url)
    connector = aiohttp.TCPConnector(resolver=PinnedIPResolver(pinned_ip))
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
    ) as session:
        async with session.request(
            method=method,
            url=validated_url,
            headers=headers,
            json=json_body,
            allow_redirects=False,
        ) as response:
            return PinnedOutboundResponse(status=response.status)
