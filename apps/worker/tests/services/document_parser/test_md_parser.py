from pathlib import Path

from app.services.document_parser import md_parser


def test_resolve_markdown_image_source_path_keeps_absolute_refs(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "job"
    image_path = output_dir / "images" / "foo.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"img")

    resolved_path = md_parser.resolve_markdown_image_source_path(
        str(output_dir),
        str(image_path),
    )

    assert resolved_path == image_path


def test_parse_md_renames_staging_style_image_refs_from_worker_cwd(
    monkeypatch,
    tmp_path: Path,
) -> None:
    worker_cwd = tmp_path / "app"
    output_dir = worker_cwd / "users" / "kb" / "job" / "Default_Root" / "job.pdf"
    image_ref = "users/kb/job/Default_Root/job.pdf/images/source.png"
    source_image = worker_cwd / image_ref
    source_image.parent.mkdir(parents=True)
    source_image.write_bytes(b"png")

    monkeypatch.chdir(worker_cwd)
    monkeypatch.setattr(
        md_parser,
        "detect_tocs_in_texts",
        lambda lines, model_name=None: (None, lines),
    )
    monkeypatch.setattr(
        md_parser,
        "eval_md_headings",
        lambda md_lines, source_type, **kwargs: md_lines,
    )
    monkeypatch.setattr(
        md_parser,
        "detect_summary_img_md",
        lambda line, last_context, output_dir, mode=False: [(image_ref, None, None)],
    )

    base_llm_paras = {
        "model_name": "deepseek-chat",
        "smart_title_parse": False,
        "summary_image": False,
        "summary_table": False,
        "summary_txt": False,
        "stopwords": [],
    }

    result_df = md_parser.parse_md(
        output_dir=str(output_dir),
        source_type="md",
        md_lines=["body line"],
        base_llm_paras=base_llm_paras,
        relative_root="doc.md",
    )

    image_rows = result_df[result_df["path"].str.startswith("images/")]
    assert len(image_rows) == 1
    assert not source_image.exists()
    assert (output_dir / image_rows.iloc[0]["path"]).exists()


def test_resolve_markdown_image_source_path_rejects_cross_job_refs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    worker_cwd = tmp_path / "app"
    output_dir = worker_cwd / "users" / "kb" / "job" / "Default_Root" / "job.pdf"
    other_job_image = worker_cwd / "users" / "kb" / "other-job" / "Default_Root" / "job.pdf" / "images" / "source.png"
    other_job_image.parent.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    other_job_image.write_bytes(b"png")

    monkeypatch.chdir(worker_cwd)

    resolved_path = md_parser.resolve_markdown_image_source_path(
        str(output_dir),
        "users/kb/other-job/Default_Root/job.pdf/images/source.png",
    )

    assert resolved_path is None


def test_parse_md_deferred_table_summary_uses_table_result_branch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        md_parser,
        "detect_tocs_in_texts",
        lambda lines, model_name=None: (None, lines),
    )
    monkeypatch.setattr(
        md_parser,
        "eval_md_headings",
        lambda md_lines, source_type, **kwargs: md_lines,
    )
    monkeypatch.setattr(
        md_parser,
        "extract_title_keywords_summary",
        lambda text, max_keywords=3, summary_len=None: (
            "LLM Table Title",
            "kw1;kw2",
            "LLM table summary",
        ),
    )

    base_llm_paras = {
        "model_name": "deepseek-chat",
        "smart_title_parse": False,
        "summary_image": False,
        "summary_table": True,
        "summary_txt": False,
        "stopwords": [],
    }
    md_lines = [
        "# Section 1",
        "<table><tr><td>Header</td></tr><tr><td>Value</td></tr></table>",
    ]

    result_df = md_parser.parse_md(
        output_dir=str(tmp_path),
        source_type="md",
        md_lines=md_lines,
        base_llm_paras=base_llm_paras,
        relative_root="doc.md",
    )

    table_rows = result_df[result_df["path"].str.startswith("tables/")]
    assert len(table_rows) == 1

    table_row = table_rows.iloc[0]
    assert table_row["keywords"] == "kw1;kw2"
    assert table_row["summary"] == "table-1\nLLM table summary"
    assert table_row["path"].startswith("tables/")
    assert table_row["path"].endswith("LLM Table Title.html")
