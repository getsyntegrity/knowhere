from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
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


def _build_profile() -> SimpleNamespace:
    return SimpleNamespace(
        route="standard",
        doc_category="generic",
    )


def _stub_pymupdf_parse(
    monkeypatch: MonkeyPatch,
    pdf_parser: Any,
    captured_calls: list[str],
) -> None:
    def fake_parse_with_pymupdf(
        pdf_path: str,
        filename: str,
        output_dir: str,
        base_llm_paras: dict,
        relative_root: str | None = None,
    ) -> pd.DataFrame:
        captured_calls.append("pymupdf")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        assert pdf_path.endswith(".pdf")
        assert filename == "source.pdf"
        assert base_llm_paras["doc_name"] == "source.pdf"
        assert relative_root == "Default_Root/source.pdf"
        return pd.DataFrame([{"content": "fallback"}])

    monkeypatch.setattr(pdf_parser, "_parse_with_pymupdf", fake_parse_with_pymupdf)


def test_should_use_pymupdf_when_mineru_keys_are_missing(
    worker_contract_environment: None,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.services.document_parser import pdf_parser

    captured_calls: list[str] = []
    monkeypatch.setattr(pdf_parser.settings, "MINERU_API_KEYS", "")
    monkeypatch.setattr(
        pdf_parser,
        "upload_and_parse",
        lambda *_args, **_kwargs: captured_calls.append("mineru"),
    )
    _stub_pymupdf_parse(monkeypatch, pdf_parser, captured_calls)

    parsed_df = pdf_parser.parse_pdfs(
        str(tmp_path / "source.pdf"),
        "source.pdf",
        str(tmp_path / "out"),
        {},
        profile=_build_profile(),
        relative_root="Default_Root/source.pdf",
        s3_key="uploads/source.pdf",
    )

    assert captured_calls == ["pymupdf"]
    assert parsed_df["content"].tolist() == ["fallback"]


def test_should_fallback_to_pymupdf_when_mineru_service_is_unavailable(
    worker_contract_environment: None,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.services.document_parser import pdf_parser
    from shared.core.exceptions.domain_exceptions import MinerUServiceException

    captured_calls: list[str] = []
    monkeypatch.setattr(pdf_parser.settings, "MINERU_API_KEYS", "token=test-key")

    def fake_upload_and_parse(*_args: Any, **_kwargs: Any) -> None:
        captured_calls.append("mineru")
        raise MinerUServiceException(internal_message="MinerU unavailable")

    monkeypatch.setattr(pdf_parser, "upload_and_parse", fake_upload_and_parse)
    _stub_pymupdf_parse(monkeypatch, pdf_parser, captured_calls)

    parsed_df = pdf_parser.parse_pdfs(
        str(tmp_path / "source.pdf"),
        "source.pdf",
        str(tmp_path / "out"),
        {},
        profile=_build_profile(),
        relative_root="Default_Root/source.pdf",
        s3_key="uploads/source.pdf",
    )

    assert captured_calls == ["mineru", "pymupdf"]
    assert parsed_df["content"].tolist() == ["fallback"]
