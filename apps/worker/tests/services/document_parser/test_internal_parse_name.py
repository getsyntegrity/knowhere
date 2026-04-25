from __future__ import annotations

from pathlib import Path

from app.services.document_parser.internal_parse_name import prepare_internal_parse_input


def test_should_normalize_the_original_filename_when_preparing_the_parse_input(
    tmp_path: Path,
) -> None:
    temp_file_path = tmp_path / "downloaded.pdf"
    temp_file_path.write_bytes(b"pdf")

    prepared = prepare_internal_parse_input(
        str(temp_file_path),
        "GB 50243-2016 通风与空调工程施工质量验收规范.pdf",
    )

    assert prepared.internal_filename == "GB_50243-2016_通风与空调工程施工质量验收规范.pdf"
    assert Path(prepared.file_path).name == prepared.internal_filename
    assert Path(prepared.file_path).exists()
    assert temp_file_path.exists() is False


def test_should_prefer_the_s3_extension_when_the_metadata_filename_is_stale(
    tmp_path: Path,
) -> None:
    temp_file_path = tmp_path / "downloaded.pdf"
    temp_file_path.write_bytes(b"pdf")

    prepared = prepare_internal_parse_input(
        str(temp_file_path),
        "legacy-upload.txt",
        fallback_ext=".pdf",
        prefer_fallback_ext=True,
    )

    assert prepared.internal_filename == "legacy-upload.pdf"
    assert Path(prepared.file_path).name == "legacy-upload.pdf"
    assert Path(prepared.file_path).exists()
    assert temp_file_path.exists() is False
