from pathlib import Path

from app.services.document_parser import parse_service


class _FakeProfile:
    file_type = "txt"
    route = "standard"
    doc_category = "generic"
    atlas_candidate = False
    page_count = 1
    reasoning = ""
    scan_type = None

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


def test_checkerboard_inject_parse_threads_job_id_to_pptx_parser(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class _FakePptxProfile:
        file_type = "pptx"
        route = "standard"
        doc_category = "generic"
        atlas_candidate = False
        page_count = 12
        reasoning = ""
        scan_type = None

        def summary(self) -> str:
            return "fake-pptx"

    monkeypatch.setattr(
        parse_service,
        "profile_document",
        lambda file_path, filename="": _FakePptxProfile(),
    )

    def fake_parse_pptx(
        file_full_path,
        filename,
        output_dir,
        base_llm_paras,
        strategy="to_pdf_api",
        job_id=None,
        relative_root=None,
        baseurl="",
    ):
        captured["file_full_path"] = file_full_path
        captured["filename"] = filename
        captured["output_dir"] = output_dir
        captured["strategy"] = strategy
        captured["job_id"] = job_id
        captured["relative_root"] = relative_root
        return "parsed-pptx"

    monkeypatch.setattr(
        "app.services.document_parser.pptx_parser.parse_pptx",
        fake_parse_pptx,
    )

    output_dir, parsed_df = parse_service.checkerboard_inject_parse(
        file_full_path=str(tmp_path / "deck.pptx"),
        filename="deck.pptx",
        output_dir=str(tmp_path / "output-root"),
        job_id="job_123",
        internal_output_filename="deck_internal.pptx",
        kb_dir="Default_Root",
        doc_type="auto",
        s3_key="uploads/deck.pptx",
    )

    assert parsed_df == "parsed-pptx"
    assert captured["filename"] == "deck.pptx"
    assert captured["strategy"] == "to_pdf_api"
    assert captured["job_id"] == "job_123"
    assert captured["relative_root"] == "Default_Root/deck.pptx"
    assert output_dir.endswith("Default_Root/deck_internal.pptx")
