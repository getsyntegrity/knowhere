from __future__ import annotations

import pytest
from pytest import MonkeyPatch


@pytest.mark.parametrize(
    ("environment", "s3_key", "expected"),
    [
        ("production", "uploads/source.pdf", True),
        ("staging", "uploads/source.pdf", True),
        ("development", "uploads/source.pdf", False),
        ("production", None, False),
    ],
)
def test_should_select_mineru_s3_url_mode_for_supported_worker_sources(
    worker_contract_environment: None,
    monkeypatch: MonkeyPatch,
    environment: str,
    s3_key: str | None,
    expected: bool,
) -> None:
    from app.services.document_parser import mineru_pdf_service

    monkeypatch.setattr(
        mineru_pdf_service.settings,
        "FORCE_MINERU_UPLOAD_ENABLED",
        False,
    )
    monkeypatch.setattr(mineru_pdf_service.settings, "ENVIRONMENT", environment)

    assert mineru_pdf_service._should_use_mineru_s3_url_mode(s3_key) is expected


def test_should_force_mineru_direct_upload_in_worker_contract(
    worker_contract_environment: None,
    monkeypatch: MonkeyPatch,
) -> None:
    from app.services.document_parser import mineru_pdf_service

    monkeypatch.setattr(
        mineru_pdf_service.settings,
        "FORCE_MINERU_UPLOAD_ENABLED",
        True,
    )
    monkeypatch.setattr(mineru_pdf_service.settings, "ENVIRONMENT", "production")

    assert (
        mineru_pdf_service._should_use_mineru_s3_url_mode("uploads/source.pdf")
        is False
    )
