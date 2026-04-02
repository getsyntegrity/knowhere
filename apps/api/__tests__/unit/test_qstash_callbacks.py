import sys
from types import SimpleNamespace

import pytest

from app.api.v1.routes import qstash_callbacks


def test_get_qstash_verification_url_prefers_public_callback_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        qstash_callbacks.app_config,
        "QSTASH_CALLBACK_BASE_URL",
        "https://api.example.com/api/v1",
        raising=False,
    )

    url = qstash_callbacks._get_qstash_verification_url(
        "/webhooks/qstash/callback",
        "http://api.internal:5005/api/v1/webhooks/qstash/callback",
    )

    assert url == "https://api.example.com/api/v1/webhooks/qstash/callback"


def test_get_qstash_verification_url_falls_back_to_request_url_when_base_url_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        qstash_callbacks.app_config,
        "QSTASH_CALLBACK_BASE_URL",
        None,
        raising=False,
    )

    url = qstash_callbacks._get_qstash_verification_url(
        "/webhooks/qstash/callback",
        "http://api.internal:5005/api/v1/webhooks/qstash/callback",
    )

    assert url == "http://api.internal:5005/api/v1/webhooks/qstash/callback"


def test_verify_qstash_signature_uses_single_derived_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verify_calls: list[str] = []

    class FakeReceiver:
        def __init__(self, current_signing_key: str, next_signing_key: str) -> None:
            assert current_signing_key == "current"
            assert next_signing_key == "next"

        def verify(
            self,
            *,
            signature: str,
            body: str,
            url: str | None = None,
            clock_tolerance: int = 0,
        ) -> None:
            assert signature == "test-signature"
            assert body == '{"ok":true}'
            assert clock_tolerance == 0
            verify_calls.append(url or "")

    monkeypatch.setattr(
        qstash_callbacks.app_config,
        "QSTASH_CURRENT_SIGNING_KEY",
        "current",
        raising=False,
    )
    monkeypatch.setattr(
        qstash_callbacks.app_config,
        "QSTASH_NEXT_SIGNING_KEY",
        "next",
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "qstash", SimpleNamespace(Receiver=FakeReceiver))

    is_valid = qstash_callbacks._verify_qstash_signature(
        b'{"ok":true}',
        "test-signature",
        "https://api.example.com/api/v1/webhooks/qstash/callback",
    )

    assert is_valid is True
    assert verify_calls == ["https://api.example.com/api/v1/webhooks/qstash/callback"]
