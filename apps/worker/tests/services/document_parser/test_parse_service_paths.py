from pathlib import Path

from app.services.document_parser import parse_service


class _FakeProfile:
    route = "standard"
    doc_category = "generic"
    reasoning = ""

    def summary(self) -> str:
        return "fake"


def test_checkerboard_inject_parse_uses_original_relative_root_and_internal_output_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict = {}
    source_filename = "spec draft.docx"
    internal_filename = "spec_draft.docx"

    def fake_profile_document(file_path: str, filename: str = "") -> _FakeProfile:
        captured["profile_file_path"] = file_path
        captured["profile_filename"] = filename
        return _FakeProfile()

    monkeypatch.setattr(parse_service, "profile_document", fake_profile_document)

    def fake_parse_texts(file_path: str, baseurl: str = ""):
        captured["parse_texts_file_path"] = file_path
        return ["body"]

    def fake_parse_md(output_dir, source_type, file_path=None, md_lines=None, base_llm_paras=None, relative_root=None):
        captured["output_dir"] = output_dir
        captured["source_type"] = source_type
        captured["relative_root"] = relative_root
        captured["md_lines"] = md_lines
        return "parsed"

    monkeypatch.setattr("app.services.document_parser.txt_parser.parse_texts", fake_parse_texts)
    monkeypatch.setattr("app.services.document_parser.md_parser.parse_md", fake_parse_md)

    output_dir, parsed_df = parse_service.checkerboard_inject_parse(
        file_full_path=str(tmp_path / internal_filename.replace(".docx", ".txt")),
        filename=source_filename,
        output_dir=str(tmp_path / "output-root"),
        internal_output_filename=internal_filename,
        kb_dir="Default_Root",
        doc_type="auto",
    )

    assert parsed_df == "parsed"
    assert captured["profile_filename"] == internal_filename
    assert captured["relative_root"] == f"Default_Root/{source_filename}"
    assert output_dir.endswith(f"Default_Root/{internal_filename}")
    assert captured["output_dir"].endswith(f"Default_Root/{internal_filename}")
