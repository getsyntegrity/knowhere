from pathlib import Path

from app.services.document_parser.internal_parse_name import (
    normalize_internal_parse_name,
    prepare_internal_parse_input,
)


def test_normalize_internal_parse_name_matches_internal_parser_path_rules() -> None:
    assert normalize_internal_parse_name(
        "GB 50243-2016 通风与空调工程施工质量验收规范.pdf"
    ) == "GB_50243-2016_通风与空调工程施工质量验收规范.pdf"


def test_normalize_internal_parse_name_uses_fallback_extension() -> None:
    assert normalize_internal_parse_name("spec draft", fallback_ext=".pdf") == "spec_draft.pdf"


def test_normalize_internal_parse_name_prefers_authoritative_fallback_extension() -> None:
    assert normalize_internal_parse_name(
        "legacy-name.txt",
        fallback_ext=".pdf",
        prefer_fallback_ext=True,
    ) == "legacy-name.pdf"


def test_prepare_internal_parse_input_moves_file_to_normalized_path(tmp_path: Path) -> None:
    temp_file_path = tmp_path / "tmp-upload"
    temp_file_path.write_bytes(b"pdf")

    prepared_parse_input = prepare_internal_parse_input(
        str(temp_file_path),
        "spec draft.txt",
        fallback_ext=".pdf",
        prefer_fallback_ext=True,
    )

    assert prepared_parse_input.internal_filename == "spec_draft.pdf"
    assert prepared_parse_input.file_path.endswith("/spec_draft.pdf")
    assert not temp_file_path.exists()
    assert Path(prepared_parse_input.file_path).read_bytes() == b"pdf"
