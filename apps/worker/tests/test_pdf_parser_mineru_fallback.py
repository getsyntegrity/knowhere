from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

_REQUIRED_CONFIG_ENVIRONMENT: dict[str, str] = {
    "DS_KEY": "test-deepseek-key",
    "DS_URL": "https://example.test/v1",
    "S3_BUCKET_NAME": "knowhere-test-bucket",
    "S3_ACCESS_KEY_ID": "test-access-key",
    "S3_SECRET_ACCESS_KEY": "test-secret-key",
    "S3_TEMP_PATH": "/tmp",
    "USERS_DATA_PATH": "/tmp/users",
    "DATABASE_URL": "postgresql+asyncpg://test:test@127.0.0.1:5432/knowhere_test",
    "SECRET_KEY": "test-secret-key",
    "TMP_PATH": "/tmp",
    "FONT_PATH": "/tmp",
    "CHROMEDRIVER_PATH": "/tmp/chromedriver",
}

for environmentName, environmentValue in _REQUIRED_CONFIG_ENVIRONMENT.items():
    os.environ.setdefault(environmentName, environmentValue)

from app.services.document_parser import pdf_parser
from shared.core.exceptions.domain_exceptions import MinerUServiceException


def _build_profile() -> SimpleNamespace:
    return SimpleNamespace(
        route="standard",
        doc_category="generic",
    )


def _stub_pymupdf_parse(
    monkeypatch: Any,
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
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    captured_calls: list[str] = []
    monkeypatch.setattr(pdf_parser.settings, "MINERU_API_KEYS", "")
    monkeypatch.setattr(
        pdf_parser,
        "upload_and_parse",
        lambda *_args, **_kwargs: captured_calls.append("mineru"),
    )
    _stub_pymupdf_parse(monkeypatch, captured_calls)

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
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    captured_calls: list[str] = []
    monkeypatch.setattr(pdf_parser.settings, "MINERU_API_KEYS", "token=test-key")

    def fake_upload_and_parse(*_args: Any, **_kwargs: Any) -> None:
        captured_calls.append("mineru")
        raise MinerUServiceException(internal_message="MinerU unavailable")

    monkeypatch.setattr(pdf_parser, "upload_and_parse", fake_upload_and_parse)
    _stub_pymupdf_parse(monkeypatch, captured_calls)

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
