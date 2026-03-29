"""Regression tests for atlas-specific parsing behavior."""

from pathlib import Path

from app.services.document_parser.atlas_parser import parse_atlas


def test_parse_atlas_keeps_unique_chunk_ids_for_identical_page_images(
    monkeypatch,
    tmp_path: Path,
):
    output_dir = tmp_path / "atlas-output"
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True)

    identical_image_bytes = b"same-rendered-page"
    (images_dir / "page-1.png").write_bytes(identical_image_bytes)
    (images_dir / "page-2.png").write_bytes(identical_image_bytes)

    child_results = iter(
        [
            {"ok": True, "total_pages": 2, "page_texts": ["A", "B"]},
            {
                "ok": True,
                "page_data": [
                    (1, "first page text", "page-1.png"),
                    (2, "second page text", "page-2.png"),
                ],
            },
        ]
    )

    monkeypatch.setattr(
        "app.services.document_parser.atlas_parser.run_in_child_process",
        lambda *args, **kwargs: next(child_results),
    )
    monkeypatch.setattr(
        "app.services.document_parser.atlas_parser._detect_toc_pages_from_texts",
        lambda *args, **kwargs: (set(), None),
    )
    monkeypatch.setattr(
        "app.services.document_parser.atlas_parser._vlm_extract_page_info",
        lambda *args, **kwargs: "sheet-info",
    )
    monkeypatch.setattr(
        "app.services.document_parser.atlas_parser.tokenize2stw_remove",
        lambda *args, **kwargs: [],
    )

    df = parse_atlas(
        pdf_path=str(tmp_path / "atlas.pdf"),
        output_dir=str(output_dir),
        base_llm_paras={"stopwords": []},
    )

    know_ids = df["know_id"].tolist()

    assert len(know_ids) == 2
    assert len(set(know_ids)) == 2
